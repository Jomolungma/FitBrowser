'use strict';
/**
 * @license
 * Copyright 2026 Google LLC. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

// Activity file parsing happens out-of-band, in activity_to_json.py. This
// page just fetches the resulting data.json and renders it on the map.

function pausedSecondsBetween(pauses, from, to) {
    let paused = 0;
    for (const pause of pauses) {
        const overlapStart = Math.max(pause.start.getTime(), from.getTime());
        const overlapEnd = Math.min(pause.end.getTime(), to.getTime());
        if (overlapEnd > overlapStart) paused += (overlapEnd - overlapStart) / 1000;
    }
    return paused;
}

function movingSecondsBetween(pauses, from, to) {
    return (to.getTime() - from.getTime()) / 1000 - pausedSecondsBetween(pauses, from, to);
}

// --- Map wiring -------------------------------------------------------

const mapElement = document.getElementById('map');

let map;
let Polyline;
let Marker;
let InfoWindow;
let infoWindow;
let currentPolyline;
let startMarker;
let endMarker;
let kmMarkers = [];
let pauseMarkers = [];

function haversineMeters(a, b) {
    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const h =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
}

function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h > 0 ? h + 'h ' : ''}${m}m ${s}s`;
}

const KM_IN_METERS = 1000;

function computeKmSplits(records, pauses) {
    const splits = [];
    const startTime = records[0].time;
    let lastSplitTime = startTime;
    let lastEle = records[0].ele;
    let cumulativeDistance = 0;
    let nextTarget = KM_IN_METERS;

    for (let i = 1; i < records.length; i++) {
        const prev = records[i - 1];
        const curr = records[i];
        const segmentStart = cumulativeDistance;
        const segmentDistance = haversineMeters(prev, curr);
        cumulativeDistance += segmentDistance;

        while (segmentDistance > 0 && nextTarget <= cumulativeDistance) {
            const fraction = (nextTarget - segmentStart) / segmentDistance;
            const lat = prev.lat + (curr.lat - prev.lat) * fraction;
            const lng = prev.lng + (curr.lng - prev.lng) * fraction;
            const time =
                prev.time && curr.time
                    ? new Date(prev.time.getTime() + (curr.time.getTime() - prev.time.getTime()) * fraction)
                    : undefined;
            const ele =
                prev.ele !== undefined && curr.ele !== undefined
                    ? prev.ele + (curr.ele - prev.ele) * fraction
                    : undefined;

            splits.push({
                km: nextTarget / KM_IN_METERS,
                lat,
                lng,
                splitSeconds: time && lastSplitTime ? movingSecondsBetween(pauses, lastSplitTime, time) : undefined,
                elapsedSeconds: time && startTime ? movingSecondsBetween(pauses, startTime, time) : undefined,
                elevationChange: ele !== undefined && lastEle !== undefined ? ele - lastEle : undefined,
            });

            if (time) lastSplitTime = time;
            if (ele !== undefined) lastEle = ele;
            nextTarget += KM_IN_METERS;
        }
    }

    return splits;
}

function clearKmMarkers() {
    kmMarkers.forEach((marker) => marker.setMap(null));
    kmMarkers = [];
}

function addKmMarkers(records, pauses) {
    clearKmMarkers();

    computeKmSplits(records, pauses).forEach(({ km, lat, lng, splitSeconds, elapsedSeconds, elevationChange }) => {
        const splitText = splitSeconds !== undefined ? formatDuration(splitSeconds) : 'n/a';
        const elevationText =
            elevationChange !== undefined
                ? `${elevationChange >= 0 ? '+' : ''}${Math.round(elevationChange)} m`
                : undefined;
        const marker = new Marker({
            position: { lat, lng },
            map,
            title: `Km ${km}: ${splitText}`,
            label: { text: String(km), fontSize: '10px', color: '#ffffff' },
            icon: {
                path: google.maps.SymbolPath.CIRCLE,
                scale: 9,
                fillColor: '#4285F4',
                fillOpacity: 1,
                strokeColor: '#ffffff',
                strokeWeight: 1.5,
            },
        });

        marker.addListener('click', () => {
            infoWindow.setContent(
                `<div><strong>Km ${km}</strong><br>Split: ${splitText}` +
                    (elapsedSeconds !== undefined ? `<br>Total: ${formatDuration(elapsedSeconds)}` : '') +
                    (elevationText !== undefined ? `<br>Elevation: ${elevationText}` : '') +
                    `</div>`,
            );
            infoWindow.open({ map, anchor: marker });
        });

        kmMarkers.push(marker);
    });
}

function clearPauseMarkers() {
    pauseMarkers.forEach((marker) => marker.setMap(null));
    pauseMarkers = [];
}

// Finds where on the track the runner was at a given time, interpolating
// between the two surrounding GPS points (or clamping to the nearest end).
function findPositionAtTime(records, time) {
    for (let i = 1; i < records.length; i++) {
        const prev = records[i - 1];
        const curr = records[i];
        if (prev.time && curr.time && prev.time <= time && time <= curr.time) {
            const span = curr.time.getTime() - prev.time.getTime();
            const fraction = span > 0 ? (time.getTime() - prev.time.getTime()) / span : 0;
            return {
                lat: prev.lat + (curr.lat - prev.lat) * fraction,
                lng: prev.lng + (curr.lng - prev.lng) * fraction,
            };
        }
    }
    const first = records[0];
    const last = records[records.length - 1];
    return first.time && time <= first.time ? { lat: first.lat, lng: first.lng } : { lat: last.lat, lng: last.lng };
}

function pauseIcon() {
    const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">' +
        '<circle cx="11" cy="11" r="10" fill="#FB8C00" stroke="#ffffff" stroke-width="1.5"/>' +
        '<rect x="7" y="6" width="3" height="10" rx="1" fill="#ffffff"/>' +
        '<rect x="12" y="6" width="3" height="10" rx="1" fill="#ffffff"/>' +
        '</svg>';
    return {
        url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
        scaledSize: new google.maps.Size(22, 22),
        anchor: new google.maps.Point(11, 11),
    };
}

function addPauseMarkers(records, pauses) {
    clearPauseMarkers();

    pauses.forEach(({ start, end }) => {
        const position = findPositionAtTime(records, start);
        const durationText = formatDuration((end - start) / 1000);
        const marker = new Marker({
            position,
            map,
            title: `Pause: ${durationText}`,
            icon: pauseIcon(),
        });

        marker.addListener('click', () => {
            infoWindow.setContent(`<div><strong>Pause</strong><br>${durationText}</div>`);
            infoWindow.open({ map, anchor: marker });
        });

        pauseMarkers.push(marker);
    });
}

function plotTrack(records, pauses, elevation, movingTimeLabel) {
    if (currentPolyline) currentPolyline.setMap(null);
    if (startMarker) startMarker.setMap(null);
    if (endMarker) endMarker.setMap(null);
    clearKmMarkers();
    clearPauseMarkers();

    const path = records.map((r) => ({ lat: r.lat, lng: r.lng }));

    currentPolyline = new Polyline({
        path,
        geodesic: true,
        strokeColor: '#EA4335',
        strokeOpacity: 0.95,
        strokeWeight: 4,
    });
    currentPolyline.setMap(map);

    const bounds = new google.maps.LatLngBounds();
    path.forEach((p) => bounds.extend(p));
    map.fitBounds(bounds);

    startMarker = new Marker({ position: path[0], map, label: 'S', title: 'Start' });
    endMarker = new Marker({
        position: path[path.length - 1],
        map,
        label: 'F',
        title: 'Finish',
    });

    addKmMarkers(records, pauses);
    addPauseMarkers(records, pauses);
}

// data.json's sport field is already one of 'running' / 'cycling' / 'moving'
// (see activity_to_json.py); this just turns it into a label for the stats bar.
function sportLabel(sport) {
    return `${sport.charAt(0).toUpperCase()}${sport.slice(1)}`;
}

// Derives the data file's URL from the page's own location by swapping its
// .html extension for .json - e.g. index.html loads index.json, foo.html
// loads foo.json - so the data file's name never has to be hardcoded here.
function dataUrlFromLocation(location) {
    return location.pathname.replace(/\.html?$/i, '.json');
}

async function loadData(location) {
    const dataUrl = dataUrlFromLocation(location);
    try {
        const response = await fetch(dataUrl);
        if (!response.ok) {
            throw new Error(`Failed to fetch ${dataUrl} (HTTP ${response.status})`);
        }
        const data = await response.json();

        const records = data.records.map((r) => ({
            lat: r.lat,
            lng: r.lng,
            time: r.time ? new Date(r.time) : undefined,
            ele: r.ele === null || r.ele === undefined ? undefined : r.ele,
        }));
        if (records.length === 0) {
            throw new Error(`No GPS records found in ${dataUrl}.`);
        }
        const pauses = data.pauses.map((p) => ({ start: new Date(p.start), end: new Date(p.end) }));

        plotTrack(records, pauses, data.elevation, sportLabel(data.sport));
    } catch (err) {
        console.error(err);
    }
}

async function loadGoogleMapsApiKey() {
    const response = await fetch('gmapikey.json');
    if (!response.ok) {
        throw new Error(`Failed to fetch gmapikey.json (HTTP ${response.status})`);
    }
    const { key } = await response.json();
    if (!key) {
        throw new Error('gmapikey.json is missing a "key" field.');
    }
    return key;
}

// location: the page's own Location object (e.g. document.location), passed
// in by the HTML that loads this module - see dataUrlFromLocation above.
async function init(location) {
    let key;
    try {
        key = await loadGoogleMapsApiKey();
    } catch (err) {
        console.error(err);
        return;
    }
    window.initGoogleMapsLoader({ key });

    const mapsLibrary = await google.maps.importLibrary('maps');
    const markerLibrary = await google.maps.importLibrary('marker');
    Polyline = mapsLibrary.Polyline;
    InfoWindow = mapsLibrary.InfoWindow;
    Marker = markerLibrary.Marker;
    // World view until a track is loaded; plotTrack then fits the map to it.
    map = new mapsLibrary.Map(mapElement, {
        center: { lat: 20, lng: 0 },
        zoom: 2,
        mapTypeId: 'terrain',
    });
    // headerDisabled removes the InfoWindow's reserved title/close-button row,
    // which otherwise leaves a blank strip above short content like ours.
    infoWindow = new InfoWindow({ headerDisabled: true });
    map.addListener('click', () => infoWindow.close());

    await loadData(location);
}

export { init };
