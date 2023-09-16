.PHONY: test
test:
	docker volume rm rmount-test-volume
	docker volume create --driver local \
	--opt type=tmpfs \
	--opt device=tmpfs \
	--opt o=uid=0 \
	rmount-test-volume
	docker build . --tag rmount-test-image
	docker run --rm -v \
      /var/run/docker.sock:/var/run/docker.sock \
	  -v rmount-test-volume:/tmp \
	  --volume /etc/fuse.conf:/etc/fuse.conf:ro \
	  --volume /etc/passwd:/etc/passwd:ro \
	  --volume /etc/group:/etc/group:ro \
	  --cap-add SYS_ADMIN \
	  --device /dev/fuse \
	  --security-opt apparmor:unconfined \
	  rmount-test-image pytest --volume-mountpoint rmount-test-volume

package:
	python setup.py bdist_wheel --plat-name $(OS)

install:
	pip install .

.ONESHELL:
static-checks:
	black . --check --preview --line-length 70
	flake8 rmount
	pylint ./rmount
	mypy rmount

publish: package
	twine upload dist/*.whl --verbose