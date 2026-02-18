import openai

# RunPod exposes port 8000 at this URL pattern
POD_ID = "17qofkn2453z5h" 
API_KEY = "sk-hit8-mistral-x7Bq9L2mZ4pW"

client = openai.OpenAI(
    base_url=f"https://{POD_ID}-8000.proxy.runpod.net/v1",
    api_key=API_KEY
)

print("🧠 Sending test prompt...")
response = client.chat.completions.create(
    model="stelterlab/Mistral-Small-24B-Instruct-2501-AWQ",
    messages=[
        {"role": "user", "content": "Veraal naar Frans en Duits: De kat krapt de krollen van de trap."}
    ],
    temperature=0.3,
    max_tokens=1000
)

print(f"🤖 Answer: {response.choices[0].message.content}")
