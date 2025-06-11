import openai
from textwrap import dedent

def generate_prank():
    troll_prompt = dedent("""
Invent a completely new, funny, over-the-top **office prank or office troll** that could happen at a software company.
Requirements:
- Make it DIFFERENT each time you write it
- It can involve Developers, QA, Management, or any other team
- Keep it SHORT (max 5 lines)
- Use plenty of fun emojis
- Do NOT always repeat the same joke style — be creative!
Generate ONE such funny prank now:
""")

    troll_resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a playful office troll."},
            {"role": "user",   "content": troll_prompt}
        ],
        temperature=0.7,
        max_tokens=200
    )
    return troll_resp.choices[0].message.content.strip()