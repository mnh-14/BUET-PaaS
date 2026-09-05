IMAGE_NAME="192.168.128.152/paas-builders/builder-image"
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <image-tag>"
    exit 1
fi
IMAGE_TAG="$1"
echo "Building image: $IMAGE_NAME:$IMAGE_TAG and $IMAGE_NAME:latest"
docker build -t "$IMAGE_NAME:$IMAGE_TAG" -t "$IMAGE_NAME:latest" .
echo "Pushing image to registry: $IMAGE_NAME:$IMAGE_TAG and $IMAGE_NAME:latest"
docker push "$IMAGE_NAME:$IMAGE_TAG" 
docker push "$IMAGE_NAME:latest"
echo "Image build and push complete for: $IMAGE_NAME:$IMAGE_TAG and $IMAGE_NAME:latest"