# Rubric generators and RL verifiers: a survey

As of 2026-10-12.

## Answer and scope

Most works use a strong frontier model to generate rubrics (Gemini-2.5-Pro, GPT-4.1, GPT-4o, o3-mini) and a cheap model as the RL judge (gpt-4o-mini, GPT-4.1-mini, or a trained 8B model). Web-app RL works use a VLM on screenshots (Qwen2.5-VL-32B or 72B), not a rubric tree.

This survey covers 24 works: the 15 that PLAN.md cites and 9 more that use rubrics or model judges as RL rewards. Few of the 24 use their rubrics as a reward in RL. Most are benchmarks only.

## Works that train a policy with RL or DPO

Six works name both the rubric generator and the RL judge: RaR, RLCF, OpenRubrics, Rubric-ARM, DR Tulu and OnlineRubrics. Three rubric-RL works (Rubicon, RCCA, RubricsTree) do not name the RL judge.

| Work | Rubric generator | Verifier / reward judge in training | Policy, algorithm |
| --- | --- | --- | --- |
| [RaR](https://arxiv.org/abs/2507.17746) (Scale AI) | GPT-4o (medicine), o3-mini (science) | gpt-4o-mini | Qwen2.5-7B, GRPO |
| [RLCF](https://arxiv.org/abs/2507.18624) (CMU, Apple) | Qwen2.5-72B-Instruct | Qwen2.5-72B-Instruct (mean of 25 samples, 0–100), plus generated verifier programs | Qwen2.5-7B(-Instruct), DPO only |
| [OpenRubrics / Rubric-RM](https://arxiv.org/abs/2510.07743) (Emory) | GPT-4.1-mini makes the data; Gemini-2.5-Flash-Lite filters it | Rubric-RM: generator and judge fine-tuned from Qwen3-8B (also 4B) | Qwen2.5-7B-Instruct, DPO |
| [Rubric-ARM](https://arxiv.org/abs/2602.01511) (Emory et al.) | Trained generator, from Qwen3-8B | Trained judge, from Qwen3-8B (the two are trained by alternating RL) | Qwen2.5-7B-Instruct, GRPO and DPO |
| [DR Tulu / RLER](https://arxiv.org/abs/2511.19399) (AI2, UW) | GPT-4.1 (initial and evolving rubrics) | GPT-4.1-mini (2025-04-14) | Qwen3-8B, GRPO variant |
| [OnlineRubrics](https://arxiv.org/abs/2510.07284) (Scale AI) | Humans; o3-mini extracts new criteria from response pairs | GPT-4.1-mini | Qwen2.5-7B-Instruct, GRPO |
| [Rubicon](https://arxiv.org/abs/2508.12790) (Ant, ZJU) | Qwen3-30B-A3B or Gemini 2.5 Pro, plus humans | "Critic models", not named | Qwen3-30B-A3B, algorithm not named |
| [RCCA](https://arxiv.org/abs/2608.27906) (Ant), web apps | Not named | "The evaluator", not named | Ling-3.0-Flash + SFT |
| [RubricsTree](https://arxiv.org/abs/2606.18203) (Google) | Human experts; the LLM router is not named | Not named for RL (the evaluation judge is Gemini-3-flash) | Qwen 0.6B / 1.7B / 4B, GRPO |
| [Kimi K2](https://arxiv.org/abs/2507.20534) (Moonshot) | Fixed core and prescriptive rubrics, plus human ones | K2 itself (pairwise self-critique); RLVR rollouts refine the critic | K2 |
| [SLM judges](https://arxiv.org/abs/2608.30005) | Dataset rubrics (RaR-Science, PointRubric) | A Qwen3-1.7B probe judge did better than an 8B generative judge (0.643 vs 0.594) and was 10.7× faster | GRPO; policy not named in the abstract |
| [WebGen-Agent](https://arxiv.org/abs/2509.22644), web | No rubric | Qwen2.5-VL-32B-Instruct gives screenshot and GUI-agent scores | Qwen2.5-Coder-7B-Instruct, Qwen3-8B; Step-GRPO |
| [ReLook](https://arxiv.org/abs/2510.11498) (Tencent), web | No rubric | Frozen Qwen2.5-VL-72B-Instruct on screenshots; a failed render gives 0 | Qwen2.5-7B-Instruct, Llama-3.1-8B-Instruct; GRPO |
| [ARGO](https://alignment.openai.com/argo/) (OpenAI) | A policy trained with RL to write rubrics | A reasoning model with the rubric; it imitates a trained reward model | No model names. It audits a reward model; it does not train a chat policy. |

## Benchmarks only (no RL)

Four benchmarks chose their judge by agreement with human labels: MiniAppBench, ArtifactsBench, PaperBench and HealthBench. Humans write the rubrics in PaperBench, Mind2Web 2, HealthBench and Agent-as-a-Judge.

| Work | Rubric generator | Judge |
| --- | --- | --- |
| [WebDevJudge](https://arxiv.org/abs/2510.18560) | gemini-2.5-pro | Many judges tested, with UI-TARS-1.5 as the GUI executor. The best ensemble (DeepSeek-V3-0324 + UI-TARS-1.5) reached only 67.6% agreement. |
| [MiniAppBench](https://arxiv.org/abs/2603.09652) | LLM plus expert domain guidelines; model not named | Gemini-3-Pro-Preview. It had the best F1 against experts out of 5 candidates (GPT-5.2, Claude-Sonnet-4.5, Qwen3-Coder-480B, GLM-4.7). |
| [WebCoderBench](https://arxiv.org/abs/2601.02430) | GPT-5-Chat, Gemini-2.5-pro and Doubao-Seed-1.6 write drafts. Humans merge them. | Gemini-2.5-pro (quality), GPT-5-chat (alignment) |
| [ArtifactsBench](https://arxiv.org/abs/2507.04952) (Tencent) | Hunyuan-Turbos writes drafts; humans refine them | Gemini-2.5-Pro (90.95% pair accuracy against humans), Qwen2.5-VL-72B (71.34%) |
| [PaperBench](https://arxiv.org/abs/2504.01848) | Humans. The paper says frontier models could not make reliable rubrics. | o3-mini-high. o1 was a little better (F1 0.84 vs 0.83) but cost 12× more. |
| [Mind2Web 2](https://arxiv.org/abs/2506.21506) | Humans; Claude-3.7-Sonnet drafts the judge scripts | o4-mini (extractor and verifier) |
| [HealthBench](https://arxiv.org/abs/2505.08775) | 262 physicians | GPT-4.1 (macro F1 0.709; o4-mini 0.692; o3 0.681) |
| [DeepResearch Bench / RACE](https://arxiv.org/abs/2506.11763) | Gemini-2.5-Pro (weights and criteria) | Gemini-2.5-Pro; Gemini-2.5-Flash for the FACT citation checks |
| [Agent-as-a-Judge](https://arxiv.org/abs/2410.10934) | Humans | Not named in the paper text |
| [Interventional transfer](https://arxiv.org/abs/2610.10809) | Qwen3.8-27B, DeepSeek-V4-Flash, Opus-5 | Gemini 3.8 Flash |

## What the survey shows

1. **A strong model generates the rubrics; a cheap model is the judge.** Rubrics are made once, before training, so their cost is low. The judge runs on every rollout, so it is small: gpt-4o-mini, GPT-4.1-mini, trained 8B models, even a 1.7B probe. RaR found that rubrics help small judges most.
2. **Benchmarks choose the judge by agreement with human labels.** HealthBench, MiniAppBench, PaperBench and ArtifactsBench did this. For PaperBench, cost decided between two judges that were almost equal.
3. **High-stakes benchmarks keep humans in the rubric loop.** WebCoderBench uses 3 LLM drafts, but humans merge them. Our plan uses an LLM merge.
4. **The judge in web-app RL is a VLM, not a rubric tree.** WebGen-Agent and ReLook use Qwen2.5-VL (32B or 72B) on screenshots and GUI runs. RCCA is the only web-app RL work with rubrics, and it does not name its generator or evaluator. No public paper uses a web-app rubric tree as an RL reward with a named judge. Our project can fill this gap.
5. **Almost all RL policies are Qwen 7–8B.** Only Ant (Qwen3-30B-A3B, Ling 124B MoE) and Moonshot (Kimi K2) train larger ones.

## What this means for our rubric-tree generator

Our default of one strong model for generation matches the literature. The hard part comes later: a judge that can check interactions.

- `RT_DRAFT_MODELS` already lets us copy the WebCoderBench idea of drafts from different model families.
- For a later RL reward, a small judge can check the leaves that are checked by viewing. Leaves checked by interaction need a GUI agent. WebDevJudge found that UI-TARS-1.5 adds only about 1 point of agreement.
- Before we choose any judge, we need human labels on our 26 queries (PLAN.md open question Q6).

## Limits of this survey

Most papers were read through a summary tool, so a few model names may need a check against the PDF. For WebDevJudge, MiniAppBench, RubricsTree and Agent-as-a-Judge, the full text was also searched. Some model names (GPT-5.6-Terra, Opus-5, Gemini 3.8 Flash) are newer than Claude's knowledge; they are given as the papers write them.

## Sources

All pages were opened on 2026-10-12. The arXiv links are in the work names in the two tables above. The other source is the [ARGO post](https://alignment.openai.com/argo/) on the OpenAI alignment blog.
