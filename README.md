# ai201-project4-provenance-guard

## Project Overview

Provenance Guard is a backend service that helps determine whether a piece of text is likely AI-generated or human-written. Instead of making a simple yes/no decision, the system combines multiple detection signals to produce a confidence score and a transparency label. The goal is to provide useful information to readers while allowing creators to appeal decisions that may be incorrect.

---

## Architecture Overview

When a creator submits text, the request is first received by the `/submit` API endpoint. The text is then analyzed by two independent detection signals:

1. **LLM-Based Classification (Groq)** – Uses an LLM to estimate whether the writing appears AI-generated or human-written based on semantic patterns and writing style.
2. **Stylometric Analysis** – Measures statistical writing characteristics such as sentence length variation, vocabulary diversity, and punctuation usage.

The outputs from both signals are combined into a single confidence score. Based on this score, the system generates one of three transparency labels:

- High-confidence AI-generated
- High-confidence Human-written
- Uncertain

The final decision, confidence score, individual signal scores, and metadata are stored in the audit log before the API returns the response to the user.

If a creator disagrees with the decision, they may submit an appeal through the `/appeal` endpoint. The appeal is linked to the original submission, its status changes to **Under Review**, and the appeal is recorded in the audit log.