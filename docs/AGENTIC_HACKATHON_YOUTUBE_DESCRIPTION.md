# YouTube description — S2PNexus demo (All Things Agentic Hackathon)

**Title suggestion:**
S2PNexus — Real Multi-Agent Handoff on Google ADK + Gemini 3.5 Flash (Fortified Enterprise Fleet)

**Description (paste as-is):**

S2PNexus is a live Source-to-Pay platform on Google Cloud. For the All Things Agentic
Hackathon's Fortified Enterprise Fleet track, we built a real 3-step multi-agent handoff on
top of it using Google's Agent Development Kit (ADK) and Gemini 3.5 Flash on Vertex AI:
requisition intake → supplier/sourcing check → receipt/invoice 3-way match — each step
grounded in real tenant data, each one logging to the same Agent Activity dashboard the
platform's other agents already use.

Disclosure: S2PNexus is a pre-existing production platform, live on Google Cloud since
late July 2026. The ADK pipeline, the Gemini 3.5 Flash upgrade, and everything shown after
1:03 in this video were built during the hackathon's Submission Period specifically for
this entry.

Architecture note: the ADK pipeline runs as its own Cloud Run service, separate from the
main backend, since google-adk needs newer FastAPI/Starlette versions than the production
backend is pinned to. Two services, two trust boundaries — the backend owns tenant data and
identity, the ADK service only ever sees data it's explicitly handed.

Chapters:
0:00 Problem & context
0:26 Value proposition
1:03 Architecture, briefly
1:44 Live demo — pipeline running through all 3 steps against real data
2:55 Proof: deployed on Google Cloud Run
3:15 Close

Live services (Google Cloud Run):
- Frontend: https://s2pnexus-frontend-120737021520.us-central1.run.app
- Backend API: https://s2pnexus-backend-120737021520.us-central1.run.app
- ADK pipeline (Agent Gateway): https://s2pnexus-adk-pipeline-120737021520.us-central1.run.app

Devpost submission: [add link once submitted]
Repo: https://github.com/pgskannan/S2PNexus (see adk-service/README.md for spin-up instructions)

Built for the All Things Agentic Hackathon (Fortified Enterprise Fleet track).
#AllThingsAgenticHackathon #GoogleADK #VertexAI #Gemini
