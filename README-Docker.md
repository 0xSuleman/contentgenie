# Run ContentGenie with Docker


First make a .env file with the API keys like this:

```bash
GEMINI_API_KEY=put_your_gemini_api_key_here
IMAGE_PROVIDER=pollinations
HUGGINGFACE_TOKEN=optional_huggingface_token_for_zimage
```


To run Dockerfile do this:
```bash
docker build -t contentgenie:latest .
docker run -p 31415:31415 --env-file .env contentgenie:latest
```
Export Docker image:
```bash
docker save contentgenie > contentgenie.tar
```
