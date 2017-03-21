PATH := node_modules/.bin:$(PATH)

.NOTPARALLEL:
.ONESHELL:

input := $(shell mktemp -u)

default: tools

tools:
	docker build --build-arg http_proxy=http://10.0.1.43:1080 -t quay.io/hotosm/oam-dynamic-tiler-tools .

server: tools
	docker build --build-arg http_proxy=http://10.0.1.43:1080 -t quay.io/hotosm/oam-dynamic-tiler-server -f server/Dockerfile .

deploy: project.json
	apex deploy

install: project.json

project.json: project.json.hbs node_modules/.bin/interp
	interp < $< > $@

node_modules/.bin/interp:
	npm install

compute-environment: node_modules/.bin/interp
	interp < aws/$@.json.hbs > $(input)
	aws batch create-compute-environment --cli-input-json file://$(input)
	rm -f $(input)

job-queue: node_modules/.bin/interp
	interp < aws/$@.json.hbs > $(input)
	aws batch create-job-queue --cli-input-json file://$(input)
	rm -f $(input)

transcode-job-definition: node_modules/.bin/interp
	interp < aws/$@.json.hbs > $(input)
	aws batch register-job-definition --cli-input-json file://$(input)
	rm -f $(input)

submit-job: node_modules/.bin/interp
	interp < $(job) > $(input)
	aws batch submit-job --cli-input-json file://$(input)
	rm -f $(input)
