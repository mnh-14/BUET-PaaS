IMAGE_NAME="192.168.128.152/paas-builders/builder-image"
IMAGE_TAG="$1"
echo "Building image: $IMAGE_NAME:$IMAGE_TAG and $IMAGE_NAME:latest"
docker build -t "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest" .
echo "Pushing image to registry: $IMAGE_NAME:$IMAGE_TAG and $IMAGE_NAME:latest"
docker push "$IMAGE_NAME:$IMAGE_TAG" "$IMAGE_NAME:latest"
echo "Image build and push complete for: $IMAGE_NAME:$IMAGE_TAG and $IMAGE_NAME:latest"