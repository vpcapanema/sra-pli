import re

def clean_output(raw):
    cleaned = re.sub(r'<thinking>.*?</thinking>', '', raw, flags=re.DOTALL)
    lines = []
    for line in cleaned.split('\n'):
        if not lines or line.strip() != lines[-1].strip():
            lines.append(line)
    return '\n'.join(lines).strip()
