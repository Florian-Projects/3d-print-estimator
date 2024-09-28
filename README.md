This is very much a prototype and not at all ready for a production deployment
# STL fillament used/ print time calculator
To runn this please install docker.
You can then run:
`docker build -t "estimator" .`
`docker run --rm -d "estimator"`

After that visit `localhost:8000` in the browser.
if you want to use different settings for the slicing process you can modify the `slicer.ini` file.
