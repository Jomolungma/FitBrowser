/*
 * Shows where activities started, one flag per place. The markers are
 * computed out-of-band by activity_map.py, which writes them to a JSON file
 * (activity_markers.json by default); the page passes that file's URL to
 * init(), which fetches it (and the Google Maps API key from gmapikey.json)
 * and renders it on the map.
 */

const mapEl = document.getElementById('map');

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url} (HTTP ${response.status})`);
    }
    return response.json();
}

async function loadGoogleMapsApiKey() {
    const { key } = await fetchJson('gmapikey.json');
    if (!key) {
        throw new Error('gmapikey.json is missing a "key" field.');
    }
    return key;
}

function plural(count) {
    return `${count} activit${count === 1 ? 'y' : 'ies'}`;
}

// The flag element for one marker, with a badge showing the group size when
// it holds more than one activity.
function flagElement(m) {
    const flag = document.createElement('div');
    flag.className = 'flag';
    flag.textContent = '\u{1F6A9}';
    if (m.count > 1) {
        const badge = document.createElement('span');
        badge.textContent = m.count;
        flag.appendChild(badge);
    }
    return flag;
}

function popupElement(m, dates) {
    const popup = document.createElement('div');
    popup.className = 'popup';
    const heading = document.createElement('h3');
    heading.textContent = plural(m.count);
    const datesEl = document.createElement('p');
    datesEl.textContent = dates;
    const sportsEl = document.createElement('p');
    sportsEl.textContent = Object.entries(m.sports).map(([s, n]) => `${s} ×${n}`).join(', ');
    const linkEl = document.createElement('p');
    const link = document.createElement('a');
    link.href = m.url;
    link.textContent = 'Show activities';
    linkEl.appendChild(link);
    popup.append(heading, datesEl, sportsEl, linkEl);
    return popup;
}

function plotMarkers(map, markers, AdvancedMarkerElement, InfoWindow) {
    const infoWindow = new InfoWindow();
    const bounds = new google.maps.LatLngBounds();

    for (const m of markers) {
        const dates = m.first === m.last ? m.first : `${m.first} – ${m.last}`;
        const marker = new AdvancedMarkerElement({
            map,
            position: { lat: m.lat, lng: m.lng },
            content: flagElement(m),
            zIndex: m.count,  // bigger groups drawn on top of nearby smaller ones
            title: `${plural(m.count)}, ${dates}`,
        });
        marker.addListener('click', () => {
            infoWindow.setContent(popupElement(m, dates));
            infoWindow.open({ map, anchor: marker });
        });
        bounds.extend(marker.position);
    }

    if (markers.length === 1) {
        map.setCenter(bounds.getCenter());
        map.setZoom(11);
    } else if (markers.length > 1) {
        map.fitBounds(bounds);
    }
}

// Derives the markers file's URL from the page's own location by swapping its
// .html extension for .json - e.g. activity_map.html loads activity_map.json -
// so the data file's name never has to be hardcoded here.
function markersUrlFromLocation(location) {
    return location.pathname.replace(/\.html?$/i, '.json');
}

// location: the page's own Location object (e.g. document.location), passed
// in by the HTML that loads this module - see markersUrlFromLocation above.
async function init(location) {
    const markersUrl = markersUrlFromLocation(location);
    try {
        const [key, markers] = await Promise.all([loadGoogleMapsApiKey(), fetchJson(markersUrl)]);
        window.initGoogleMapsLoader({ key });

        const { Map, InfoWindow } = await google.maps.importLibrary('maps');
        const { AdvancedMarkerElement } = await google.maps.importLibrary('marker');
        const map = new Map(mapEl, { center: { lat: 20, lng: 0 }, zoom: 2, mapId: 'DEMO_MAP_ID' });

        plotMarkers(map, markers, AdvancedMarkerElement, InfoWindow);
        const total = markers.reduce((n, m) => n + m.count, 0);
    } catch (err) {
        console.error(err);
    }
}

export { init };
