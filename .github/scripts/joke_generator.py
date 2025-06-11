import openai

def generate_clean_pr_joke():
    joke_resp = openai.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            { "role": "system", "content": "You are a witty developer assistant." },
            { "role": "user",   "content": "Tell me a short, fun programming joke about clean code reviews." }
        ],
        temperature=0.8,
        max_tokens=40
    )
    return joke_resp.choices[0].message.content.strip()