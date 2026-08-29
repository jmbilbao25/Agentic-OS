---
captured: 2026-08-29
captured_at: 2026-08-29T03:54:57Z
kind: research
topic: context engineering for LLM agents
source: automations/research.py
results: 18
---

# Research — context engineering for LLM agents

Gathered from 3 source(s), 18 result(s). **Unverified capture** — distil into `brain/wiki/` in your own words before relying on any of it.

## hf-papers

- [PILOT in the Loop: Live Self-Improvement for Long-Horizon Agents](https://huggingface.co/papers/2608.26530) · **25**
  Long-horizon agent runs generate experience that can improve both the current run and future work. Most self-improvement methods process this experience only after execution ends, so they cannot redirect the active run or immediately apply and validate lessons learned from it. We argue that self-improvement should inst
- [Agentic Game Development as a Verifiable Trajectory Data Engine for Scaling World Models](https://huggingface.co/papers/2608.25518) · **120**
  A common strategy for scaling world models is to train on more crawled video with more compute. We argue that this strategy is inefficient: scaling world models also requires a recursive data engine that offers grounded reward signals. The success of code agents illustrates why this matters. As code is executable, comp
- [GameWAM: A World Action Model for Video Games](https://huggingface.co/papers/2608.26200) · **38**
  Modern video games combine first-person perception, rapid visual changes, persistent world state, and heterogeneous native controls. Existing game agents map visual and task context directly to actions but lack explicit world dynamics modeling, whereas interactive game world models predict visual futures from supplied 
- [CaSKG: Counterfactual-Causal Skill Graphs for Scalable Agent Skill Retrieval](https://huggingface.co/papers/2608.25500) · **5**
  Reusable skill libraries allow large language model (LLM) agents to reuse procedural knowledge across tasks, but they also turn memory access into a challenging retrieval problem. Full-library prompting preserves coverage at high context cost, vector retrieval returns compact neighborhoods but treats skills as independ
- [Training Agents to Evolve with Their Harness: TaoLive Digital Avatar Agent Technical Report](https://huggingface.co/papers/2608.15763) · **43**
  AI-powered digital avatar streamers must answer product questions, engage viewers, and execute marketing strategies in real time, demanding low latency, frequent strategy updates, and accurate yet effective responses. Evolvable Harnesses, whose Skills, Hooks, prompts, and tools can be updated independently of model wei
- [CaRGo-T: Causal Reasoning Graph-of-Thought improves Multimodal Humor Comprehension](https://huggingface.co/papers/2608.23172) · **6**
  Large-scale vision-language models (VLMs) have demonstrated remarkable versatility across a wide range of multimodal tasks. However, understanding humor remains challenging because humorous content often depends on subtle interactions among entities, events, context, and implicit relationships across image and text mod

## github

- [Meirtz/Awesome-Context-Engineering](https://github.com/Meirtz/Awesome-Context-Engineering) · **3287**
  🔥 Comprehensive survey on Context Engineering: from prompt engineering to production-grade AI systems. hundreds of papers, frameworks, and implementation guides for LLMs and AI agents.
- [tigicion/dao-code](https://github.com/tigicion/dao-code) · **1255**
  Open-source TypeScript terminal coding agent for DeepSeek-V4 — builds on DeepSeek's strong price-performance and ultra-cheap cache pricing, engineering byte-stable prefixes and cache-reusing forks so cross-session memory and a continuous self-correction layer add almost no token cost; 1M context, Skills/MCP/Hooks, Clau
- [ratel-ai/ratel](https://github.com/ratel-ai/ratel) · **429**
  Context engineering for AI agents. ~80% fewer tokens. Fix tool overload. Skills and memory with in-process BM25 and semantic retrieval. Progressive Disclosure. No vector DB.
- [yzfly/awesome-context-engineering](https://github.com/yzfly/awesome-context-engineering) · **130**
  A curated collection of resources, papers, tools, and best practices for Context Engineering in AI agents and Large Language Models (LLMs).
- [rossoctl/context-guru](https://github.com/rossoctl/context-guru) · **43**
  Context engineering manages an agentic system's context: persisting and efficiently retrieving conversations and trajectories for the purpose of optimizing LLM context, this may include compacting and summarizing context to reduce costs and latency while preserving accuracy.
- [GoogleCloudPlatform/db-context-enrichment](https://github.com/GoogleCloudPlatform/db-context-enrichment) · **39**
  A context engineering agent designed to generate, manage, and optimize structured context sets from your database schemas. It bridges the gap between Large Language Models (LLMs) and databases by compiling, evaluating, and maintaining the precise operational context needed for highly accurate natural language-to-SQL qu

## hackernews

- [Show HN: Geniusrise, an open source framework and ecosystem for AI agents](https://github.com/geniusrise/geniusrise) · **9**
  9 points · 2 comments
- [Show HN: No Hype AI – get oriented in using LLM tools for software engineering](https://nohypeai.dev) · **9**
  9 points · 0 comments
- [Show HN: ArchGW – An intelligent edge and service proxy for agents](https://github.com/katanemo/archgw/) · **118**
  118 points · 15 comments
- [Launch HN: Datafruit (YC S25) – AI for DevOps](https://news.ycombinator.com/item?id=45104974) · **65**
  65 points · 48 comments
- [Launch HN: MindFort (YC X25) – AI agents for continuous pentesting](https://news.ycombinator.com/item?id=44117465) · **60**
  60 points · 24 comments
- [Launch HN: TeamOut (YC W22) – AI agent for planning company retreats](https://app.teamout.com/ai) · **55**
  55 points · 61 comments

---

## Open questions

- [ ] what does this change about how the OS should work?
- [ ] which single claim here would be most expensive to be wrong about?
- [ ] is there an existing note this contradicts? reconcile, don't append.
