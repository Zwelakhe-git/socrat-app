#!/bin/bash
echo "opening container " $1
sudo docker exec -it $1 /bin/bash
