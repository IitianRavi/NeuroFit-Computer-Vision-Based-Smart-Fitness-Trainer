from services.config.workout_config import PROMPT


class LLMCoach:
    def __init__(self, groq_client):
        self.client = groq_client
        self.history = []
        self.system_prompt = PROMPT

    def give_feedback(self, event, issue, language="Hindi, using natural Hinglish gym terms", context=None):
        prompt = f"Event: {event}"

        if issue:
            prompt += f" Form Issue: {issue}"
        elif context:
            prompt += f" Pose Feedback: {context}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-10:],
            {"role": "user", "content": f"{prompt}\nSpeak in {language}. Use the natural script for that language, keep common gym terms understandable, and do not switch to English."}
        ]

        response = self.client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            temperature=0.4,
        )

        text = response.choices[0].message.content.strip()
        self.history.append({"role": "assistant", "content": text})

        return text
    
