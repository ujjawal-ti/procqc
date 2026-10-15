# Detecting wrong tool / object / ingredient errors: what the literature says (4 Oct 2026)

Two web literature searches were run on 4 Oct 2026, after the frame-based check (v2-v4, see
`docs/benchmarks/2026-10-01_wrong_tool_check.md`) was found not to work reliably.
1. Methods and benchmarks for substitution errors in procedural video.
2. Small VLMs, and getting a usable confidence from them.

Many sources are 2026 arXiv preprints. Two papers' tables only partly parsed (noted below). The sources
were read by research agents and not re-checked one by one.

## 1. How well can this error be detected today?

No published zero-shot result isolates substitution well. The closest numbers:

| Benchmark (error type) | Best zero-shot | Trained | Source |
|---|---|---|---|
| EgoPER "Step Modification" (other tool or ingredient) | about 42.7 average, 10.2-60.2 by task (metric unclear, likely EDA) | - | ZeProM, [arXiv 2606.21579](https://arxiv.org/html/2606.21579) (2026) |
| CaptainCook4D "Preparation Error" | recall 51.7 seen / 56.0 unseen recipes (zero-shot with reasoning); precision not reported | recall 69.0 / 76.9 (Qwen2.5-VL-7B, GRPO) | Post-training VLMs for video mistake detection, [arXiv 2608.28406](https://arxiv.org/html/2608.28406) (2026); table partly parsed |
| EgoPER "Utensil" | 0.0 plain zero-shot, 69.7 with reasoning | 91.2 | same |
| EgoOops (incorrect object use, mispick) | only overall mAP@0.3 2.5 | - | [arXiv 2410.05343](https://arxiv.org/html/2410.05343) |
| Synthetic wrong-noun swaps (MATT) | GPT-4o F1 89.4 (EPIC-KITCHENS), 51.7 (Ego4D) | 91.3 / 57.3 | [CVPR 2026, arXiv 2511.20525](https://arxiv.org/html/2511.20525) |

* Plain zero-shot often answers "correct" for everything (F1 0 in arXiv 2608.28406).
* Synthetic swaps pair a clip with another clip's instruction, so they do not test a real substitution in
  the scene.
* EgoPER files a wrong target container ("water into the wrong bowl") under "Slip", not under
  Modification. Assembly101 has "wrong position". A wrong target needs to know where the item ends up,
  not what is in the hand.
* Robot failure detection: on FailBench (2,197 robot attempts), the best model reaches 0.77 balanced
  accuracy, and no model passes 0.60 on contact-heavy assembly
  ([arXiv 2609.03611](https://arxiv.org/html/2609.03611v1)). Scale's robot-data QC found narrow checks on
  "contact sheets" of frames beat broad VLM judgement
  ([blog, Jul 2026](https://labs.scale.com/blog/from-video-review-to-measurement)).

Our v1 (narration) and v4 (frames) results are in the same range as these zero-shot numbers.

## 2. Design patterns with evidence

**Find the moment, zoom, identify, then compare.** Detect hand-object contact or use within the step,
crop or zoom on the object in hand, identify it, and compare it with the procedure in a separate step.
* Cropping to the region that matters added 2.4 points on FailBench.
* Letting GPT-5 sample frames and zoom (TAMA) raised ProMQA-Assembly accuracy from 58.7 to 67.0, mostly
  through zoom ([arXiv 2510.00161](https://arxiv.org/html/2510.00161)). Qwen2.5-VL and InternVL3 got
  worse with the same tools.
* An industrial cascade runs a contact classifier, then an open-vocabulary detector on the active
  object ([ICIAP 2025, arXiv 2507.13326](https://arxiv.org/abs/2507.13326)).
* Hand-object detectors: 100DOH ([arXiv 2006.06669](https://arxiv.org/pdf/2006.06669)), EgoHOS
  ([ECCV 2022](https://arxiv.org/pdf/2208.03826)), Hands23 contact types
  ([NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/file/612a7948f3294a02a63d970566ca8536-Paper-Conference.pdf)).
* Video-language models tell objects apart much better than actions (EgoHOIBench, LaViLa 74.3 vs 46.6,
  [ICLR 2025](https://arxiv.org/abs/2405.17719)). A 2026 survey describes a "noun shortcut": models name
  the most visible object, not the one in the acting hand
  ([arXiv 2608.18671](https://arxiv.org/html/2608.18671); the survey's interpretation).

**Confidence: answer probabilities or agreement, never self-reports.**
* VLM self-reported confidence is broadly miscalibrated
  ([EMNLP 2025](https://aclanthology.org/2025.emnlp-main.74/);
  [TrustNLP 2024](https://aclanthology.org/2024.trustnlp-1.13/)).
* One small study (Qwen2-VL-2B, n = 100) is relevant. Self-reported confidence was nearly constant
  (0.87-0.90) and ranked errors at chance (AUROC about 0.50). The answer-token probability reached AUROC
  0.92-0.99 ([arXiv 2607.22034](https://arxiv.org/html/2607.22034v1)). Our v2-v4 self-reports were all
  0.85 or more.
* Combining both signals beats either one ([arXiv 2604.17274](https://arxiv.org/abs/2604.17274)).
* Agreement across repeated samples is the practical option when probabilities are not available.
  ZeProM used 5 samples at temperature 0.7, gaining 4.7 AUC.
* Ego4D-PMD turns answers with probability below 0.6 into "unsure" and sets the threshold on validation
  data ([EMNLP 2025](https://aclanthology.org/2025.emnlp-main.706.pdf)).
* Gemini logprobs: Vertex supported them for 2.5 Flash. Users report them rejected on the Developer API
  (from Oct 2025), on Gemini 3/3.1 on Vertex (from Mar 2026), and on the OpenAI-compatible endpoint
  ([Google AI forum](https://discuss.ai.google.dev/t/openai-api-compatibility-and-logprobs/94970)).
  Fuelix is undocumented and has to be tested.

**Question format.**
* Presence questions carry a strong "yes" bias. In POPE, small VLMs said yes to 95-100% of questions
  ([EMNLP 2023](https://arxiv.org/abs/2305.10355)). In first-person video, accuracy fell to chance when
  the object asked about was present but not being used
  ([EgoIllusion, EMNLP 2025](https://arxiv.org/abs/2508.12687)). So "is a tool being used?" is a weak
  first question.
* Naming the expected object in the prompt pulls answers toward it
  ([arXiv 2601.05201](https://arxiv.org/abs/2601.05201); [V-FAT](https://arxiv.org/abs/2601.04897)).
  This is the v1 narration failure: the narrator wrote the expected item.
* Decomposition is mixed. Direct GPT-4o scored 69.2% against 55.4% with decomposed self-dialog
  (Ego4D-PMD). Decomposing only when needed works better than always decomposing
  ([EMNLP Findings 2024](https://aclanthology.org/2024.findings-emnlp.107/);
  [NeurIPS 2023](https://arxiv.org/abs/2310.17050)).
* Multiple-choice options can be answered by shortcuts from the options alone
  ([arXiv 2507.02856](https://arxiv.org/abs/2507.02856)). Shuffling the options and keeping the
  expected one unmarked limits this.

## 3. Small VLMs

* "laya-vision" (thaitea/laya-vision, Sept 2026): 201M parameters, cut down from SmolVLM-256M. It takes
  one image per question and has no video input. It is calibrated by temperature per question type
  (ECE 0.041 on its validation sets), but the weights are **CC BY-NC-SA 4.0 (non-commercial)** and the
  authors call it experimental. Early users report confident false positives
  ([HF](https://huggingface.co/thaitea/laya-vision); [Show HN](https://news.ycombinator.com/item?id=49767430)).
  Not suitable.
* The best small open video VLMs are Qwen3-VL 4B/8B (Apache 2.0, MVBench 68.9 / 68.7, Ollama/MLX on a
  Mac; [arXiv 2511.21631](https://arxiv.org/abs/2511.21631)), then InternVL3.5 and Molmo2.
* Small models trail large ones by about 15-30 points on hand-object recognition.
  * HanDyVQA: 7B models 42-55% against Gemini-2.5-Pro 72.6% ([arXiv 2512.00885](https://arxiv.org/abs/2512.00885)).
  * EOC-Bench: Qwen2.5-VL-7B 43.1% against Gemini-2.0-Flash 57.4% ([arXiv 2506.05287](https://arxiv.org/abs/2506.05287)).
  * In both, more frames and higher resolution helped.

## 4. Design chosen for v5 (decided 4 Oct 2026)

Fuelix Gemini (gemini-3.8-flash) throughout, with denser frames around the moment of use and zoomed crops.
1. **Find the moment.** Scan the step span with many small frames, and find when the hand or gripper
   touches or uses something in the role.
2. **Zoom.** Take dense full-resolution frames around that moment, plus enlarged crops around the hand
   and the object it uses.
3. **Identify, closed question.** The options are the expected item, look-alikes, "bare hand / gripper,
   no tool" and "other". The expected item is not marked, and the options are shuffled over repeated
   asks. Confidence comes from answer probabilities if Fuelix returns them, otherwise from agreement
   across the asks.
4. **Decide.** Confidently different is flagged, confidently specified passes, and anything uncertain
   goes to review. The threshold is set on the development recordings, then frozen.
5. **Measure once** on unseen CaptainCook4D recipes, with the gold rule fixed from label text before
   any run.
