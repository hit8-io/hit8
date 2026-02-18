import openai

# Replace with the POD ID you just got (e.g., "v7qofkn2453z5h")
POD_ID = "p6qb611hsgf0ke" 
API_KEY = "sk-hit8-mistral-x7Bq9L2mZ4pW" # TEI ignores this unless --api-key was set, but the client needs a string

client = openai.OpenAI(
    base_url=f"https://{POD_ID}-8000.proxy.runpod.net/v1",
    api_key=API_KEY
)

# Text to embed
text_input = "De kat krabt de krullen van de trap."

print(f"🧠 Sending text to embed: '{text_input}'")

try:
    response = client.embeddings.create(
        model="BAAI/bge-m3", # Name must match, though TEI often accepts "default" too
        input=text_input
    )

    # Extract the vector
    vector = response.data[0].embedding

    print(f"✅ Success! Embedding generated.")
    print(f"📏 Vector Dimensions: {len(vector)}") # Should be 1024 for BGE-M3
    print(f"🔢 First 5 float values: {vector[:5]}")

except Exception as e:
    print(f"❌ Error: {e}")
