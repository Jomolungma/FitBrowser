.PHONY: all exe dist test clean

all: dist

exe:
	pyinstaller --onefile --windowed \
		--add-data fitbrowser/index.css:fitbrowser \
		--add-data fitbrowser/activity.js:fitbrowser \
		--add-data fitbrowser/overview.js:fitbrowser \
		fitbrowser.py

dist:
	python -m build

lint:
	pylint fitbrowser

test:
	pytest --cov=fitbrowser --cov-report html

clean:
	rm -rf __pycache__ */__pycache__
	rm -rf .pytest_cache .coverage htmlcov
	rm -rf dist build fitbrowser.egg-info fitbrowser.spec
	find . -name '*~' -exec rm {} \;
