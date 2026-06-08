from google import genai

client = genai.Client(
    vertexai=True,
    project="project-7e952389-6c64-4d4e-9d4",
    location="us-central1",
)
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="How does AI work?",
)
print(response.text)