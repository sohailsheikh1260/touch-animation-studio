"""App configuration.

Put your Groq API key here (chat tab uses it). Never commit real keys.
You can also set the GROQ_API_KEY environment variable or a GROQ_API_KEY
line in the `.env` file — this file takes priority.
"""


BODY_PARTS = [
  "head",
  "body",
  "hand_left_upper",
  "hand_left_lower",
  "hand_right_upper",
  "hand_right_lower",
  "leg_left_upper",
  "leg_left_lower",
  "leg_right_upper",
  "leg_right_lower",
  "lip_happy",
  "lip_idle",
  "lip_scared",
  "lip_angry",
  "lip_shocked",
  "hand_left_open",
  "hand_right_open",
  "hand_left_close",
  "hand_right_close",
  "hand_left_point",
  "hand_right_point",
]