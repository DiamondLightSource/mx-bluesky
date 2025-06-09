#!/bin/bash
# Run pyheap against a pid
PID=$1
mkdir -p heap-dumps
UID=`id -u`
GID=`id -g`
podman run \
	--rm \
	--pid=host \
	--userns=keep-id:uid=$UID,gid=$GID \
	--cap-add=SYS_PTRACE \
	--volume $(pwd):/heap_dumps \
	ivanyu/pyheap-dumper:latest \
	--pid $PID \
	--file /heap-dumps/heap.pyheap
