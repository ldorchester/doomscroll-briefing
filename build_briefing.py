from datetime import datetime

html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Daily Briefing</title>
</head>
<body>
  <h1>Daily Briefing</h1>
  <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
  <p>Pipeline is working.</p>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("index.html generated")
