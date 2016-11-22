deps.zip: Dockerfile
	docker run --rm --entrypoint cat $$(docker build -q .) /tmp/task.zip > $@

clean:
	rm -f deps.zip
