IMAGE_NAME="192.168.128.152/paas-builders/deploy-service-image"
IMAGE_TAG="$1"
docker build -t "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest" .
docker push "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest"