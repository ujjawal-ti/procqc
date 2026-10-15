# Published error-type distributions in procedural-mistake datasets

Compiled 2026-09-24 from primary sources (arXiv / CVF papers, official GitHub repos, official download pages). Purpose: ground the injection mix of a synthetic procedural-error benchmark in what open datasets actually annotate.

Two kinds of numbers appear below and are always labelled:

- **Published** — printed in the paper or on the official page (quoted, with URL).
- **Tallied from the released annotation file** — computed here by reading the official annotation download. These are not paper figures. The file, field and method are stated each time so they can be reproduced.

Target taxonomy used for mapping (Section 3): omission, addition, repetition, misordering, wrong tool/object (incl. wrong ingredient), early termination, correction/recovery, step-parameter deviation (wrong measurement, timing, technique, temperature).

---

## 1. Dataset sections

### 1.1 CaptainCook4D (Peddi et al., NeurIPS 2024 Datasets and Benchmarks)

- Paper: https://arxiv.org/abs/2312.14556 (HTML: https://arxiv.org/html/2312.14556v4)
- Project: https://captaincook4d.github.io/captain-cook/
- Annotations repo: https://github.com/CaptainCook4D/annotations
- Video downloader: https://github.com/CaptainCook4D/downloader

**Scale (published).** Abstract: "384 recordings (94.5 hours) of people performing recipes in real kitchen environments ... 5.3K step annotations and 10K fine-grained action annotations". Sec. 3.1: "24 cooking recipes sourced from WikiHow"; "eight participants in 10 different kitchens".

**Normal vs error recordings.** Published only as a per-recipe bar chart (Figure 4, "the total count and the durations of normal and error recordings for each recipe"); no totals in text. Tallied from `annotation_json/error_annotations.json` (`is_error` flag over 384 recordings): **220 error recordings, 164 normal**.

**Taxonomy (published, Sec. 3.2).** "(1) Preparation Error when they use soiled/wrong ingredients or use different tools, (2) Measurement Error when they use wrongly measured ingredients, (3) Timing Error when they perform a step in shorter or longer duration than what is prescribed ... (4) Temperature Error when they set higher/lower power levels in the microwave or on a stove than what is prescribed (5) Missing Step when they omit to perform a step (6) Technique Error when they perform the required action incorrectly, leading to a wrong outcome than expected. (7) Order Error when they execute steps out of the required sequence." The released `error_category_idx.json` adds an eighth tag, `Other` (index 7), not shown in the paper.

**Per-type counts (published, Figure 3 bottom-right, "statistics on the error categories in the dataset derived from the compiled annotations of all recordings").** Unit = error tags attached to step segments.

| Error type (paper name) | Count (Fig. 3) | Share of 2,566 |
|---|---|---|
| Order Errors | 795 | 31.0% |
| Technique Errors | 502 | 19.6% |
| Preparation Errors | 410 | 16.0% |
| Measurement Errors | 331 | 12.9% |
| Missing Steps | 285 | 11.1% |
| Timing Errors | 177 | 6.9% |
| Temperature Errors | 66 | 2.6% |
| **Total** | **2,566** | |

**Cross-check, tallied from `error_annotations.json`** (field `step_annotations[].errors[].tag`): 5,700 step segments; 1,964 steps with at least one error tag; 532 steps with more than one tag; 2,574 tags = the seven Figure 3 counts exactly, plus `Other` 8 (0.3%). So one step often carries two tags (e.g. a Measurement Error and an Order Error on the same step), which matters for pooling (Section 4).

**Downloads.**
- Annotations alone: yes, public GitHub (CSV and JSON, plus task graphs and splits). `error_annotations.json` is 2.0 MB.
- Raw video: yes, via Box links in `metadata/download_links.json`, pulled by the downloader scripts. Modalities: GoPro 360p and 4K, HoloLens 360p RGB, HoloLens depth/AB/poses/IMU/audio. Total size in GB is **not published**; README states only that the 3D archives are "on the order of several terabytes".
- License: dataset "Apache License, Version 2.0" (paper App. C.3.5; project site). Note the annotations repo's `LICENSE` file is MIT and the arXiv listing's "CC BY 4.0" refers to the paper text.

### 1.2 EgoPER (Lee, Lu, Zhang, Hoai, Elhamifar, CVPR 2024)

- Paper (CVF, returns 403 to some fetchers; downloads with a browser user agent): https://openaccess.thecvf.com/content/CVPR2024/papers/Lee_Error_Detection_in_Egocentric_Procedural_Task_Videos_CVPR_2024_paper.pdf
- Author copy: https://www.khoury.northeastern.edu/home/eelhami/publications/cvpr24_EgoPER.pdf ; supplement: https://www.khoury.northeastern.edu/home/eelhami/publications/cvpr24_suppmat_EgoPER.pdf
- Repo: https://github.com/robert80203/EgoPER_official
- No arXiv version found.

**Scale (published, Sec. 3.2).** "386 untrimmed videos with 213 normal and 173 erroneous videos for a total of 28 hours of footage"; 5 tasks (pinwheels, quesadilla, oatmeal, coffee, tea); "11 participants at two different environments using Microsoft HoloLens2"; 1280x720 at 15 fps.

**Table 1 (published), quoted:**

```
                Normal Videos            Erroneous Videos
Task        # Vid.  Min.  # Actions   # Vid.  Min.  Avg # errors
Coffee        32    8.4     24          35    9.3     2.2
Pinwheels     42    5.6     14          42    4.2    10.8
Tea           47    2.6     11          32    2.5     4.9
Quesadilla    48    1.6      9          32    1.8     4.9
Oatmeal       44    4.2     12          32    4.3     4.6
```
Caption: "The average number of errors per video reflects repetitive actions, e.g., not inserting toothpicks 5 times will be counted as 5." Multiplying `# Vid.` by `Avg # errors` gives roughly 77 / 454 / 157 / 157 / 147 error segments per task, about 990 in total (arithmetic, not a published figure).

**Taxonomy (published, Sec. 3.2 "Error Taxonomy").** "We define error as any deviation from the task graph." Five step types: **Step Omission** ("skipping one or multiple steps"), **Step Addition** ("unnecessary extra steps that are not in the task graph"), **Step Modification** ("performing a step in a different way than the one specified by the recipe, e.g., using a different tool ... or using different ingredients ... This does not necessarily change the outcome"), **Step Slip** ("executing a step in a way that leads to not achieving the goal of the step ... a slip is an error that needs corrective action(s) subsequently"), **Step Correction** ("performing an action to mitigate the effect of an slip error"). Errors were scripted from a hand-built task graph.

**Per-type counts: not published.** Neither the paper nor the supplement gives instance counts per error type. Supplement S.4, Tables 2 to 6 list the error-step *classes* per type per task. Tallying those class lists (column assignment for a few short entries inferred from layout): Omission 17, Addition 9, Modification 15, Slip 18, Correction 10 classes (69 total); Coffee is slip-heavy (10 slip classes). These are class counts, not instance counts.

**Downloads.** No public URL. README: "Please send an email with the following information to lee.shih@northeastern.edu for downloading our datasets and annotations"; "The shared link will be expired in two weeks." Files on request: `annotation.json`, `active_object.json`, `{task}_videos.zip`, `{task}_other_modalities.zip`, split files, I3D and VideoCLIP features. Size and license: **not published**.

### 1.3 HoloAssist (Wang et al., ICCV 2023)

- Paper: https://arxiv.org/abs/2309.17024
- Project: https://holoassist.github.io/ ; annotation README: https://holoassist.github.io/data_links/README.html
- Repo: https://github.com/Ember-HoloAssist/holoassist-release

**Scale (published).** "HoloAssist contains 166 hours of data captured by 222 diverse participants forming 350 unique instructor-performer pairs and carrying out 20 object-centric manipulation tasks"; "2,221 sessions" (Table 2 caption); split 1545 / 213 / 463 sessions (Sec. 5). Website says 169 hours. "414 coarse-grained actions ... 1887 fine-grained actions" are class counts; the total number of fine-grained segments is not printed.

**Mistake attribute (published names, supplement S.4.2 and annotation README, "Action Correctness").** Values: "Correct action"; "Wrong action, corrected by instructor verbally"; "Wrong action, corrected by performer"; "Wrong action, not corrected"; "Others". Sec. 3.2: "Each fine-grained action is labeled as either correct or mistake ... for benchmark evaluation, we will consolidate them into one mistake class." Only published proportion (Sec. 4.2): "the class distribution is highly skewed, with around 6% mistakes among the fine-grained actions." **Per-category counts are not published.**

**Tallied from the released annotation file** `data-annotation-trainval-v1_1.json` (https://hl2data.z5.web.core.windows.net/holoassist-data-release/data-annotation-trainval-v1_1.json, 117 MB, train+val only = 1,758 sessions; test annotations are not in the file). Field: events with `label == "Fine grained action"`, attribute `Action Correctness`.

| Action Correctness value (as stored) | Count | Share of 149,253 fine-grained actions |
|---|---|---|
| Correct Action | 141,691 | 94.93% |
| Wrong Action, corrected by instructor verbally | 4,052 | 2.71% |
| Wrong Action, corrected by student | 3,061 | 2.05% |
| otherwise | 357 | 0.24% |
| Wrong Action, not corrected | 92 | 0.06% |
| **All non-correct** | **7,562** | **5.07%** |

Of the 7,205 labelled wrong actions, 7,113 (98.7%) were corrected (instructor 4,052; performer 3,061) and 92 were not. Free-text `Incorrect Action Explanation` exists per wrong action (e.g. "Wrong place.", "The battery is upside down.", "The student drops the lens by accident.") but no error-type category.

Intervention attribute (`Conversation Purpose`, 32,392 conversation events, same file): "correct the wrong action" 3,019 (instructor-start) + 147 (instructor-reply) = 3,166; "confirming the previous action" 6,482 + 272; "follow-up instruction" 7,891 + 534; "describing high-level instruction" 7,334; closing 1,734; opening 853; "adjusting to capture better quality video" 338; other/questions 3,788. Counts per intervention type are **not published** in the paper (Table 8 only says "The classes in the benchmark are highly skewed").

**Downloads.** Raw video: `video_pitch_shifted.tar` 184.20 GB, `video_compress.tar` 144.62 GB (base https://hl2data.z5.web.core.windows.net/holoassist-data-release/). Annotations alone: yes, the JSON above (111 MB listed, 117 MB measured). License: CDLA-Permissive-2.0.

### 1.4 IndustReal (Schoonbeek et al., WACV 2024)

- Paper: https://arxiv.org/abs/2310.17323
- Repo: https://github.com/TimSchoonbeek/IndustReal
- Data: https://data.4tu.nl/datasets/b008dd74-020d-4ea4-a8ba-7bb60769d224 (DOI 10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v2)

**Scale (published).** Table 1: 84 recordings, 5.8 h, 27 participants, 36 parts; two procedures (assembly of a STEMFIE toy car; maintenance = replace part of rear chassis). "75 fine-grained action classes and a total of 9,273 instances". "724 correct procedure step completions (8.6 +/- 1.2 correct completions per recording) and 38 incorrect step completions." "26.9K video frames (13% of total) are annotated for ASD, of which 3,569 frames show error states." 22 defined states plus 27 error states.

**Taxonomy (published, Table 1 caption).** "PEs: procedural errors (omission, execution order), EEs: execution errors (component installed incorrectly)". Sec. 1: "IndustReal features 38 errors, of which 14 are exclusive to the validation and test sets." Sec. 4.4.3: "In total, 35 videos (42%) contain a missing or incorrectly completed procedure step." Errors range "from minor, difficult-to-observe mistakes (e.g. installing the wheels without washers), to large mistakes, such as forgetting a wheel"; participants received "one or two instructions with errors" and also made unscripted errors.

**Per-type counts: not published.** The split of the 38 errors into omission / order / incorrect installation is not given. No correction label exists (PSR labels mark step completions; `PSR_labels_with_errors.csv` adds "entries for wrongly executed steps").

**Downloads.** Total 77.07 GB on 4TU; `all_rgb_videos.zip` 4.96 GB; per-split zips 4.4 to 10.2 GB. Annotations alone: `action_recognition_labels.zip` (68 KB) on 4TU; PSR/OD labels sit inside each recording folder. License: Apache 2.0.

### 1.5 Assembly101 (Sener et al., CVPR 2022) and "Every Mistake Counts in Assembly" (Ding et al., 2023)

- Paper: https://arxiv.org/abs/2203.14712 ; project https://assembly-101.github.io/
- Mistake follow-up: https://arxiv.org/abs/2307.16453 ; mistake CSVs: https://github.com/assembly-101/assembly101-mistake-detection
- Main annotations: https://github.com/assembly-101/assembly101-annotations (no mistake column; mistake labels live only in the repo above)
- Videos: https://huggingface.co/datasets/cvml-nus/assembly101 (gated)

**Scale (published).** "362 unique sequences of people assembling and disassembling 101 'take-apart' toy vehicles ... 8 static and 4 egocentric viewpoints, with 4321 sequences totalling 513 hours"; 1,013,523 fine-grained segments (ego-only: 167 h, 1,425 videos, 331,310 segments).

**Mistake labels (published, Sec. 4.4).** "We annotate the coarse assembly segments with a parallel set of labels {'correct', 'mistake', 'correction'}." "Of the 60k coarse actions in assembly, 15.9% and 6.7% segments are mistake and corrective segments, respectively." Absolute counts and per-toy counts: not published.

**Ding et al. 2023, Table 1 "Six types of mistakes in Assembly101" (published)**, over 328 sequences / 3,988 steps with (verb, this, that) part-level annotation:

| Verb | Coarse label | Remark (fine type) | Count |
|---|---|---|---|
| attach | correct | correct step | 2,914 |
| attach | mistake | generic order | 153 |
| attach | mistake | accumulated (consequence of an earlier mistake) | 46 |
| attach | mistake | misorientation | 156 |
| detach | mistake | unnecessary | 371 |
| detach | correction | correction | 348 |

Sec. 1: "nearly 60% of the sequences contained at least one mistake. 27.4% of these were action ordered incorrectly." Misorientation is "shown in grey as it is beyond the scope of our work."

**Tallied from the released CSVs** (328 files in `annots/`, columns `start,end,verb,this,that,label,remark`; 3,964 rows): label `correct` 2,927; `mistake` 707; `correction` 330. Remarks on mistakes: "shouldn't have happened" 377, "wrong order" 163, "wrong position" 108, "previous one is (a) mistake" 59 (spelling variants merged). The repo tally differs slightly from Table 1 (707 vs 726 mistakes; 330 vs 348 corrections), so the paper table and the file are two snapshots.

**Downloads.** Videos: Hugging Face, "Total file size: 3.89 TB", gated. Annotations alone: yes, public GitHub (mistake CSVs, a few hundred bytes each) and Google Drive for the main annotations. License: CC BY-NC 4.0.

### 1.6 EgoOops (Haneji et al., ICCV 2025 Workshop SAUAFG; arXiv 2410.05343)

- Paper: https://arxiv.org/abs/2410.05343 ; camera-ready https://openaccess.thecvf.com/content/ICCV2025W/SAUAFG/papers/Haneji_EgoOops_A_Dataset_for_Mistake_Action_Detection_from_Egocentric_Videos_ICCVW_2025_paper.pdf
- Project: https://y-haneji.github.io/EgoOops-project-page/
- Annotations: https://github.com/Y-Haneji/EgoOops-annotations (`meta/metadata.json`, `meta/mistake_classes.json`)
- Videos: https://www.lsta.media.kyoto-u.ac.jp/resource/data/EgoOops/videos-processed-720p.zip (Content-Length 5,624,517,940 bytes, about 5.6 GB)

**Scale (published).** "50 egocentric videos totaling 6.8 hours across five tasks" (electrical circuits, color mixture, ionic reaction, toy building blocks, cardboard crafts; 10 videos each); 538 annotated segments; 4 participants; 4K 30 fps head-mounted. Per task "five of 10 recordings contain mistakes that the participants performed intentionally"; the other five "still contain mistakes due to their careless errors."

**Scope (published).** "We define mistakes as 'deviations from instructional steps.' ... we consider executions mistakes in this study." Order mistakes (skipping, swapping) are deliberately excluded: "We leave the study of the other types of mistakes to future work."

**Per-type counts (published, Table 3 "The number of mistake labels", total 95).** Quote: "In total, EgoOops contains 95 execution mistakes ... the two most frequent labels are incorrect-object-picking (label 2) and wrong-way (label 5)."

| Label (paper short name / `mistake_classes.json` string) | Count | Share |
|---|---|---|
| Incorrect-object-use / "working with wrong objects" | 20 | 21.1% |
| Incorrect-object-picking / "grasping wrong objects and releasing them without using" | 24 | 25.3% |
| Self-correction / "correction of mistake actions" | 7 | 7.4% |
| Accidental-mistakes / "unintended actions" | 11 | 11.6% |
| Wrong-way / "working in the wrong way or moving" | 21 | 22.1% |
| Other-mistakes / "others" | 12 | 12.6% |

Per-task rows (EC / CM / IR / BB / CB): Object 9/4/0/2/5; Mispick 5/8/3/5/3; Correction 1/0/1/5/0; Accident 2/2/5/1/1; Way 3/5/6/5/2; Others 2/3/4/1/2. Tallying `labels` in the released `metadata.json` reproduces 20 / 24 / 7 / 11 / 21 / 12 exactly.

**Downloads.** Annotations alone: yes (public GitHub, CC BY-SA 4.0). Videos: yes, 5.6 GB zip. License: CC BY-SA 4.0.

### 1.7 EPIC-Tent (Jang et al., ICCV Workshops 2019)

- Paper: https://openaccess.thecvf.com/content_ICCVW_2019/papers/EPIC/Jang_EPIC-Tent_An_Egocentric_Video_Dataset_for_Camping_Tent_Assembly_ICCVW_2019_paper.pdf
- Annotations: https://github.com/youngkyoonjang/EPIC_Tent2019 (`Synchronised_error_label.txt`, 73 KB)
- Data: https://data.bris.ac.uk/data/dataset/2ite3tu1u53n42hjfh3886sa86 (166.8 GB; "Non-Commercial Government Licence for public sector information v2")

**Scale (published).** Paper: 24 participants, "over 5.4 hours", 1,171,897 frames, 921 action instances, 12 subtasks. The released annotation file and data.bris deposit cover 29 participants ("over 7 hours" on the project site). Two egocentric cameras (GoPro, SMI eye tracker), gaze, self-rated uncertainty for participants 8 to 24.

**Taxonomy (published, Sec. 3.1 "Error Labelling").** "Two observers annotated the eye tracking videos for errors including: 1) Motor errors, 2) misuse of equipment, 3) steps out of order, 4) equipment failure, 5) omission of a step, 6) searching for an item, 7) correction of a prior error, 8) slowness in movement, and 9) repetition. All errors were annotated with begin and end times, except omission. Ordering errors were marked for the duration of the out of order subtasks, where the correct order was defined as the sequence in the printed instructions." README code map: `{0:'motor', 1:'misuse', 2:'order', 3:'failure', 4:'omit', 5:'search', 6:'correction', 7:'slow', 8:'repeat'}`. No further definition of "motor" or "misuse" is given in the paper.

**Per-type counts: not published in the paper.** Tallied from the official `Synchronised_error_label.txt` (626 rows, 29 subjects, column `error_label_main`; `error_label_sub` is set on only 2 rows, both "misuse"):

| Code | Type | Count | Share of 626 |
|---|---|---|---|
| 0 | motor | 219 | 35.0% |
| 1 | misuse | 162 | 25.9% |
| 2 | order | 136 | 21.7% |
| 3 | failure (equipment) | 42 | 6.7% |
| 5 | search | 32 | 5.1% |
| 4 | omit | 16 | 2.6% |
| 7 | slow | 8 | 1.3% |
| 6 | correction | 8 | 1.3% |
| 8 | repeat | 3 | 0.5% |

The 626 total matches the "Epic-Tent 626" entry in Table 1 of arXiv 2511.20525. PREGO (CVPR 2024, https://arxiv.org/abs/2404.01933) and Differentiable Task Graph Learning (NeurIPS 2024, https://arxiv.org/abs/2406.01486) use only order + omit + correction + repeat (163 labels) as "procedural" mistakes and exclude motor, misuse, failure, search, slow; their EPIC-Tent-O split is 14 train / 15 test videos, with no per-type counts published.

### 1.8 ATA — Anomalous Toy Assembly (Ghoddoosian et al., ICCV 2023)

- Paper: https://openaccess.thecvf.com/content/ICCV2023/papers/Ghoddoosian_Weakly-Supervised_Action_Segmentation_and_Unseen_Error_Detection_in_Anomalous_Instructional_ICCV_2023_paper.pdf ; supplement zip: https://openaccess.thecvf.com/content/ICCV2023/supplemental/Ghoddoosian_Weakly-Supervised_Action_Segmentation_ICCV_2023_supplemental.zip
- Data request page: https://usa.honda-ri.com/ata (university affiliation required; size and license text not published)

**Scale (published).** "1152 untrimmed RGB videos, totaling 24.8 hours, with a resolution of 1920x1080 and a frame rate of 30 fps"; 32 participants; 3 toys; 4 synchronized third-person views; 15 atomic actions; "141 unique action sequences with an average length of 12.9 action segments per video". Split 972 / 36 / 144 videos.

**Taxonomy (published).** (a) Sequential anomalies, unlabeled: "redundant actions (e.g., inserting an extra screw or unexpected background segments between actions), skipped actions (e.g., not tightening a screw), and major changes in the order of training action subsequences". (b) Video-level error labels, 11 classes (supplement Table 2): idle time, dropped item w/o pickup, missing part, missing ring, missing leg, unfastened leg, unfastened screw, missing screw, extra screw, extra ring, no balancing. "Out of the 144 test videos, 40 videos are error-free and 104 are erroneous. Each test video has a max of 5 error instances with an average of 1.7 unique errors."

**Per-type counts: not published in text** (Figure 2 bar chart only). Labels are video-level, not temporally localized. Not pooled.

### 1.9 Datasets checked that do not publish error-type counts

- **CSV / SVIP** (Qian et al., CVPR 2022; https://arxiv.org/abs/2112.06447 ; https://svip-lab.github.io/dataset/CSV_dataset.html ; https://github.com/svip-lab/SVIP-Sequence-VerIfication-for-Procedures-in-Videos). 1,940 videos, 14 chemistry tasks, 5 scripted procedures each (70), 106 steps; deviations are scripted "deletions, additions, and order exchanges" and encoded only as a procedure ID. Test set split into "alter-number" (additions/deletions) and "alter-order"; only AUC per split is reported, no counts. Download via OneDrive/Baidu links in the repo; size and license not published.
- **BRIO-TA** (Moriwaki et al., ICIP 2022, DOI 10.1109/ICIP46576.2022.9897369; sample repo https://github.com/Tarmo-moriwaki/BRIO-TA_sample). "Anomalies are further categorized into incorrect processes, omissions, and abnormal durations"; 75 videos = 30 normal + 45 anomalous, one anomaly type per video; per-type counts not published; access by e-mail, academic only.
- **IndustReal** (Section 1.4): 38 errors, no type split.
- **EgoPER** (Section 1.2): five types, no instance counts.
- **HoloAssist** (Section 1.3): mistake vs correct only, no type.
- **ProMQA** (Hasegawa et al., NAACL 2025; https://arxiv.org/abs/2410.22211 ; https://github.com/kimihiroh/promqa ; Apache-2.0): 401 QA pairs on CaptainCook4D; *question*-type counts Missing 148, Next 158, Order 20, Measurement 17, Preparation 14, Technique 9, Temperature 10, Timing 25. **ProMQA-Assembly** (LREC 2026; https://arxiv.org/abs/2509.02949): 646 QA pairs on 227 Assembly101 recordings. These count questions, not annotated errors.
- **EgoProceL** (ECCV 2022; https://sid2697.github.io/egoprocel/): key-steps only; reports natural variation "average 0.12 missing steps ratio" and "average 0.49 repeated steps ratio", not error labels. **HA-ViD** (NeurIPS 2023; https://arxiv.org/abs/2307.05721): no error annotation. **Ego4D-PMD** (EMNLP 2025; https://arxiv.org/abs/2412.11927): synthetic frame/text mistakes (incomplete execution, wrong verb, wrong noun, both), balanced by construction.
- "Ego-ADR" is the method name in the EgoErrorVQA paper (Adaptive Decoupled Reasoning), not a dataset. No primary source found for "EgoMistake", "ErrorDet", "ErrorBench" or "CaptainCook4D-Mistake" as datasets.

### 1.10 EgoErrorVQA (Li et al., 2026; benchmark built on four datasets)

- Paper: https://arxiv.org/abs/2608.24134 (HTML https://arxiv.org/html/2608.24134)
- Repo: https://github.com/z1oong/EgoErrorVQA (QA JSON only; videos from the source datasets)

**Scale (published, Table 2).** 1,859 video samples across 31 procedural tasks: CaptainCook4D 1,000; EgoOops 215; Epic-Tent 184; Assembly101 460. 3,560 open-ended QA pairs; 1,857 multiple-choice samples.

**Taxonomy (published, Appendix D).** Eight categories: Wrong Object; Wrong Action; Wrong Order; Omission; Unintended and Unnecessary Action; Correct Wrong Action; Equipment Failure; Others. Distribution shown only as Figure 2(f) pie; **no numbers in text.**

**Tallied from the released QA JSON** (`data/json/*`): the files keep each source dataset's own labels, not the eight-way taxonomy.
- `captaincook4d_qa_pairs_updated.json`: 960 samples, 328 `is_error`, 431 tags: Order 137, Technique 77, Preparation 72, Measurement 55, Missing Step 50, Timing 28, Temperature 11, Other 1 (a subsample of CaptainCook4D; do not add to 1.1).
- `assembly101_qa_pairs_updated.json`: 446 segments, `error_label` correct 341 / mistake 77 / correction 28 (subsample of 1.5).
- `egooops_qa_pair.json`: 215 segments, 40 `is_error`; `error_labels`: "working with wrong objects" 11, "grasping wrong objects and releasing them without using" 10, "working in the wrong way or moving" 7, "others" 5, "unintended actions" 4, "correction of mistake actions" 3.
- `epic_tent_qa_pair.json`: 184 segments, 60 `is_error`; `error_label_main` is an integer code 0 to 6 (20 / 9 / 15 / 6 / 5 / 4 / 1) whose meaning is not documented in the repo.

License: Apache 2.0 (code). Videos must be obtained from each source.

### 1.11 PIE-V (Loginova and Keller, 2026) — synthetic mistake injection on Ego-Exo4D

- Paper: https://arxiv.org/abs/2604.15134 ; code https://github.com/ologin/PIE-V ; CC BY 4.0

Taxonomy (published): Deletion, Insertion, Substitution, Transposition, Wrong Execution, plus Correction as recovery. Benchmark: 17 tasks, 50 scenarios, "PIE-V injects 102 mistakes and 27 recovery corrections". **Per-type breakdown of the 102: not published.** Audit of existing datasets (Table 3, 25 videos each): "Error Validity" (deviation would plausibly change the outcome) EgoPER 51%, EgoOops 72%, Assembly101 65%, CaptainCook4D 74%; no per-type breakdown. Table 4 gives mistake-step rates for generated scripts (e.g. GPT-5.2+PIE-V 141/1323 = 10.66% of steps are mistakes). Relevant as a precedent for injection design; no natural distribution.

### 1.12 Mistake Attribution / MisEngine (Li, Jain, Bellos, Corso, CVPR 2026)

- Paper: https://arxiv.org/abs/2511.20525 ; project https://yayuanli.github.io/MATT/

Synthetic mistake datasets EPIC-KITCHENS-M (>221K samples) and Ego4D-M (>257K) built by an automated engine; taxonomy is by semantic role (which slot of the instruction is violated), temporal point-of-no-return, and spatial location, not by procedural type. Per-type counts not in abstract; not used for pooling.

### 1.13 Ego-Exo4D (Grauman et al., CVPR 2024)

Keystep annotation docs (https://docs.ego-exo4d-data.org/annotations/keystep/) expose `step_id`, `step_name`, `is_essential` and timing; **no mistake or error field**. Listed here because a 2025 review (arXiv 2510.19292, Table I) marks it as carrying procedural-error annotations; the released schema does not support that.

### 1.14 Robot-demonstration and robot-execution failure datasets

These annotate *robot* or *teleoperator* failures, mostly execution-level. They are kept separate from the human procedural-video pool in Section 4 and summarised in their own table.

**REFLECT / RoboFail** (Liu et al., CoRL 2023; https://arxiv.org/abs/2306.15724 ; https://robot-reflect.github.io/ ; code https://github.com/columbia-ai-robotics/reflect). Sec. 4: "100 failure scenarios, with 10 cases for each of the 10 tasks" in AI2-THOR (manually injected) plus "11 tasks with a total of 30 failure scenarios" on a real UR5e. Figure 4 taxonomy with percentages (base not stated, presumably the 130 scenarios): Planning failures 55% = wrong actions 21%, missing actions 18%, wrong action order 11%, ambiguous reference 5%; Execution failures 45% = failed execution low-level 15%, failed execution environment 13%, unexpected dynamics 11% ("Object dropped"), perception error 6%. Data directory (https://www.cs.columbia.edu/~liuzeyi/reflect_data) returned 403; size not stated. Paper CC BY 4.0, code MIT.

**FAIL-Detect** (Xu et al., 2025; https://arxiv.org/abs/2503.08558). No failure taxonomy or counts published; success rates only.

**AHA / FailGen** (Duan et al., ICLR 2025; https://arxiv.org/abs/2410.00371 ; https://github.com/NVlabs/AHA). Seven failure modes (Sec. 3.1): Incomplete Grasp (No_Grasp), Inadequate Grip Retention (Slip), Misaligned Keyframe (Translation), Incorrect Rotation (Rotation), Missing Rotation (No_Rotation), Wrong Action Sequence (Wrong_action: "performing an action keyframe before the correct one"), Wrong Target Object (Wrong_object). 49k train pairs over 79 RLBench tasks, about 11k test pairs. **Per-mode counts not published**; data regenerated by script, not hosted.

**RoboMIND** (Wu et al., 2024/2025; https://arxiv.org/abs/2412.13877 ; https://huggingface.co/datasets/x-humanoid-robomind/RoboMIND, gated, 12.3 TB, Apache-2.0 badge; `failure_data` folder). "We also release 5k trajectories of the robot task failure cases" including human-operator failures, "identified, categorized, and documented". Per-category counts for the 5k demos: **not published**. QA criteria (Fig. 4, no counts): Touch Excess; Movement not Smooth; Secondary Grabbing; Mechanical Arm Shaking; Collision before Grabbing; Image Distortion; Failed Placement; Gripper out of the Camera. Appendix F, Fig. 15 gives *policy rollout* failure shares (e.g. UR: Inaccurate Positioning 23.5%, Object Drop 17.6%, Cannot Approach Object 11.8%, Cannot Close Gripper 11.8%, Cannot Release Gripper 11.8%; Franka: Inaccurate Positioning 60.0%, Cannot Close Gripper 26.7%). RoboMIND 2.0 (https://arxiv.org/abs/2512.24653) lists twelve inspection categories (Unintended Contact, Unsmooth Motion, Re-grasping, Pre-grasp Collision, Data Anomalies, Failed Placement, Trajectory Abnormality, Excessive Speed, Visual Artifacts, Robot Arm Abnormality, Non-standard Operation, Target Displacement); counts not published.

**FAILURE dataset / FINO-Net** (Inceoglu et al., 2023; https://arxiv.org/abs/2305.04639). Baxter, 324 recordings (151 success, 173 failure). Table II totals: Success 152; Collision 77; Miss 22; Overflow 25; Spill 20; Overturn 28. Download URL not given in paper.

**ViFailback** (Zhou et al., CVPR 2026; https://arxiv.org/abs/2512.02787 ; https://huggingface.co/datasets/sii-rhos-ai/ViFailback-Dataset, 513 GB, MIT). 5,202 real ALOHA trajectories (657 success / 4,545 failed), 100 tasks, 58,128 VQA pairs. Shares on the HF card: Task Planning 12.40%; Gripper 6D-Pose 53.27%; Gripper State 18.99%; Human Intervention 2.71%. Definitions: "Task planning – Errors in the high-level task plan, such as targeting an incorrect interaction object or location"; "Gripper 6d-pose – The gripper fails to reach its correct position or orientation"; "Gripper state – The gripper does not close or open properly ..."; "Human intervention – Disruptions from external forces".

**Guardian / FailCoT** (Pacaud et al., 2025; https://arxiv.org/abs/2512.01946 ; https://huggingface.co/collections/paulpacaud/robotic-failure-detection-dataset-and-model-guardian). Table I: RLBench-Fail 12,358 execution + 5,808 planning; BridgeDataV2-Fail 7,830 + 4,880; UR5-Fail 140 + 140; total 20,188 execution / 10,820 planning. Planning sub-types: Wrong object manipulated; Wrong object state or placement; Wrong order; Missing subtask; Contradictory subtasks. Execution sub-types: No gripper close; Wrong object state or placement; Wrong object manipulated; Imprecise grasping/pushing; (BridgeV2) Task-execution semantic mismatch; Revert action. **Per-sub-type counts not published.**

**RoboFAC** (2025; https://arxiv.org/abs/2505.12224 ; https://huggingface.co/datasets/MINT-SJTU/RoboFAC-dataset, 25.8 GB, MIT). 9,440 erroneous + 1,282 successful trajectories, 78,623 QA pairs. Six failure types: Step Omission, Wrong Object (task planning); Position Deviation, Orientation Deviation (motion planning); Grasping Error, Timing Error (execution). Per-type counts not published.

**Others with taxonomy but no per-type counts:** RoboVAD (https://arxiv.org/abs/2609.17843 ; Zenodo https://zenodo.org/records/22754659; 1,570 anomaly events; Failed grasp / Collision / Object drop / Placement failure / Object not dropped), REBOOT (https://arxiv.org/abs/2609.22591 ; Misalignment / Premature release / Jamming / Off-axis collision; counts only per task phase), DenseReward (https://arxiv.org/abs/2607.13033 ; Success / Collision / Miss / Fall / Smooth / Recover), LabRobFail (https://arxiv.org/abs/2607.23704 ; 11 types incl. Sequence Reversal, Step Omission; counts only in a figure), BotFails (https://huggingface.co/datasets/kantine/BotFails), AgiBot World 2026 (https://huggingface.co/datasets/agibot-world/AgiBotWorld2026 ; "failure recovery data constitute approximately one percent" of 1,001,552 trajectories; `error_cause` field, values not enumerated on the card). FailBench (https://arxiv.org/abs/2609.03611): 2,197 attempts, 1,176 failures, per-source counts, "approximately 75% of benchmark failures are organic"; no manipulation-type counts. Large teleoperation corpora carry only outcome flags: DROID ("roughly 16k trajectories ... labeled as 'not successful'"), RH20T (0-9 completion rating; counts not published).

---

## 2. Mapping of dataset types onto the target taxonomy

Target types: **OM** omission, **AD** addition, **RP** repetition, **MO** misordering, **WT** wrong tool/object (incl. wrong ingredient), **ET** early termination, **CR** correction/recovery, **PD** step-parameter deviation (measurement, timing, technique, temperature). **UN** = unmappable.

| Dataset | Dataset type (exact name) | Target | Note |
|---|---|---|---|
| CaptainCook4D | Missing Step | OM | |
| CaptainCook4D | Order Error | MO | |
| CaptainCook4D | Preparation Error | WT | "soiled/wrong ingredients or ... different tools" |
| CaptainCook4D | Measurement Error | PD | |
| CaptainCook4D | Timing Error | PD | |
| CaptainCook4D | Temperature Error | PD | |
| CaptainCook4D | Technique Error | PD | "perform the required action incorrectly" |
| CaptainCook4D | Other | UN | 8 tags, free text |
| EgoPER | Step Omission | OM | no counts |
| EgoPER | Step Addition | AD | no counts |
| EgoPER | Step Modification | WT | "different tool ... different ingredients"; some cases are PD |
| EgoPER | Step Slip | PD | execution failure needing correction; closest is technique |
| EgoPER | Step Correction | CR | no counts |
| HoloAssist | Wrong action, corrected by instructor / by performer | CR (status only) | mistake type unknown; not pooled by type |
| HoloAssist | Wrong action, not corrected | UN (type unknown) | |
| IndustReal | procedural error: omission | OM | no split of the 38 |
| IndustReal | procedural error: execution order | MO | no split |
| IndustReal | execution error: component installed incorrectly | PD | no split |
| Assembly101 (Ding) | mistake: generic order | MO | |
| Assembly101 (Ding) | mistake: accumulated | UN | consequence of an earlier mistake, not a new deviation |
| Assembly101 (Ding) | mistake: misorientation ("wrong position") | PD | orientation/technique |
| Assembly101 (Ding) | mistake: unnecessary detach ("shouldn't have happened") | AD | extra off-procedure action |
| Assembly101 (Ding) | correction | CR | |
| EgoOops | Incorrect-object-use | WT | |
| EgoOops | Incorrect-object-picking | WT | grasped wrong object and released; attempted wrong object |
| EgoOops | Wrong-way | PD | |
| EgoOops | Self-correction | CR | |
| EgoOops | Accidental-mistakes ("unintended actions") | UN | slips/accidents; could be argued as AD |
| EgoOops | Other-mistakes | UN | |
| EPIC-Tent | order | MO | |
| EPIC-Tent | omit | OM | |
| EPIC-Tent | repeat | RP | |
| EPIC-Tent | correction | CR | |
| EPIC-Tent | misuse (of equipment) | PD | undefined in paper; could be WT |
| EPIC-Tent | motor, failure (equipment), search, slow | UN | non-procedural behaviour |
| ATA | missing part/ring/leg/screw | OM | video-level, counts in figure only |
| ATA | extra screw, extra ring | AD | idem |
| ATA | unfastened leg/screw, no balancing | PD | idem |
| ATA | idle time, dropped item w/o pickup | UN | idem |
| ATA | sequential anomalies: redundant / skipped / order changes | RP / OM / MO | unlabeled |
| CSV | deletions / additions / order exchanges | OM / AD / MO | scripted, counts not published |
| BRIO-TA | incorrect processes / omissions / abnormal durations | MO or WT / OM / PD | counts not published |
| EgoErrorVQA | Wrong Object; Wrong Action; Wrong Order; Omission; Unintended and Unnecessary Action; Correct Wrong Action; Equipment Failure; Others | WT; PD; MO; OM; AD; CR; UN; UN | re-annotation of other datasets; pie chart only |
| PIE-V | Deletion; Insertion; Substitution; Transposition; Wrong Execution; Correction | OM; AD; WT; MO; PD; CR | synthetic, no per-type counts |
| REFLECT (robot) | missing actions; wrong action order; wrong actions; ambiguous reference | OM; MO; WT; UN | planning failures |
| REFLECT (robot) | failed execution low-level / environment; unexpected dynamics; perception error | UN | execution failures, not procedural |
| AHA / FailGen (robot) | Wrong Action Sequence; Wrong Target Object; No_Grasp, Slip, Translation, Rotation, No_Rotation | MO; WT; PD | synthetic, no counts |
| RoboFAC (robot) | Step Omission; Wrong Object; Position/Orientation Deviation; Grasping Error; Timing Error | OM; WT; PD; PD; PD | no counts |
| Guardian (robot) | Missing subtask; Wrong order; Wrong object manipulated; Wrong object state or placement; Contradictory subtasks; Revert action | OM; MO; WT; PD; UN; CR | only planning/execution totals |

**Target types with no natural instance counts anywhere:** *early termination* (no dataset labels it; ATA/IndustReal "missing part" and EgoPER omission absorb it) and *repetition* (only EPIC-Tent, 3 labels; CaptainCook4D repeated steps are recorded as repeated step IDs in `recording_id_step_idx.json` but not flagged as errors; EgoProceL reports a 0.49 repeated-step ratio as natural variation).

---

## 3. Per-dataset percentages (sanity check for the pool)

Only datasets with per-type counts enter. Percentages are of each dataset's own total including unmappable labels.

| Target type | CaptainCook4D (n=2,574) | Assembly101 / Ding (n=1,074) | EgoOops (n=95) | EPIC-Tent (n=626) |
|---|---|---|---|---|
| Omission | 285 (11.1%) | 0 | 0 | 16 (2.6%) |
| Addition | 0 | 371 (34.5%) | 0 | 0 |
| Repetition | 0 | 0 | 0 | 3 (0.5%) |
| Misordering | 795 (30.9%) | 153 (14.2%) | 0 | 136 (21.7%) |
| Wrong tool/object | 410 (15.9%) | 0 | 44 (46.3%) | 0 |
| Early termination | 0 | 0 | 0 | 0 |
| Correction/recovery | 0 | 348 (32.4%) | 7 (7.4%) | 8 (1.3%) |
| Step-parameter deviation | 1,076 (41.8%) | 156 (14.5%) | 21 (22.1%) | 162 (25.9%) |
| Unmappable | 8 (0.3%) | 46 (4.3%) | 23 (24.2%) | 301 (48.1%) |

Zeros mean the dataset does not annotate that type at all (not that it was observed zero times). CaptainCook4D has no addition, repetition or correction labels; Assembly101's part-level labels cannot express omission or wrong-object; EgoOops excludes order errors by design.

## 4. Pooled distribution

**4a. Pooled by raw count (4 datasets, 4,369 labels; 3,991 after dropping unmappable).**

| Target type | Pooled count | % of 4,369 | % of 3,991 mapped |
|---|---|---|---|
| Omission | 301 | 6.9% | 7.5% |
| Addition | 371 | 8.5% | 9.3% |
| Repetition | 3 | 0.1% | 0.1% |
| Misordering | 1,084 | 24.8% | 27.2% |
| Wrong tool/object | 454 | 10.4% | 11.4% |
| Early termination | 0 | 0.0% | 0.0% |
| Correction/recovery | 363 | 8.3% | 9.1% |
| Step-parameter deviation | 1,415 | 32.4% | 35.5% |
| Unmappable | 378 | 8.7% | — |

**4b. Equal-weight mean of per-dataset shares (mapped labels only), to remove CaptainCook4D's 59% weight in the pool.**

| Target type | Mean of 4 dataset shares | Per-dataset shares (CC4D, A101, EgoOops, EPIC-Tent) |
|---|---|---|
| Omission | 4.0% | 11.1 / 0 / 0 / 4.9 |
| Addition | 9.0% | 0 / 36.1 / 0 / 0 |
| Repetition | 0.2% | 0 / 0 / 0 / 0.9 |
| Misordering | 21.9% | 31.0 / 14.9 / 0 / 41.8 |
| Wrong tool/object | 19.3% | 16.0 / 0 / 61.1 / 0 |
| Early termination | 0.0% | 0 / 0 / 0 / 0 |
| Correction/recovery | 11.5% | 0 / 33.9 / 9.7 / 2.5 |
| Step-parameter deviation | 34.0% | 41.9 / 15.2 / 29.2 / 49.8 |

**4c. Pool without CaptainCook4D (1,425 mapped labels):** omission 1.1%, addition 26.0%, repetition 0.2%, misordering 20.3%, wrong tool/object 3.1%, correction 25.5%, step-parameter deviation 23.8%.

**4d. Robot-failure percentages (not poolable with the above; percentages of different bases).**

| Source | Base | Shares |
|---|---|---|
| REFLECT / RoboFail (Fig. 4) | 130 injected/teleop failures | wrong actions 21%, missing actions 18%, wrong action order 11%, ambiguous reference 5%, exec low-level 15%, exec environment 13%, unexpected dynamics 11%, perception 6% |
| ViFailback (HF card) | 5,202 real teleop trajectories | task planning 12.40%, gripper 6D-pose 53.27%, gripper state 18.99%, human intervention 2.71% |
| FAILURE / FINO-Net (Table II) | 173 failures | collision 77, miss 22, overflow 25, spill 20, overturn 28 |
| Guardian (Table I) | 31,156 generated failures | execution 20,188 (64.8%), planning 10,820 (34.7%) |
| RoboMIND App. F | policy rollouts, per robot | Inaccurate Positioning 23.5% to 60.0% depending on arm; Object Drop up to 20% |

Reading across REFLECT and Guardian's planning sub-taxonomies, robot-side "procedural" failures are dominated by wrong object/action (21%) and missing step (18%) over wrong order (11%), the opposite ranking to the human cooking data (CaptainCook4D: order 31%, missing 11%).

**Correction rate reference points (for deciding how many injected errors should be followed by a fix):** HoloAssist 7,113 of 7,205 labelled wrong actions were corrected (98.7%, instructor 56%, performer 43%; tallied from the release file); Assembly101 348 corrections for 726 mistakes (Ding Table 1; 6.7% vs 15.9% of coarse segments in the CVPR 2022 paper); EgoOops 7 corrections per 95 mistakes; EPIC-Tent 8 per 626 labels; PIE-V injects 27 corrections per 102 mistakes.

---

## 5. Caveats

1. **CaptainCook4D dominates the raw pool (59% of labels; 76% of mapped step-parameter deviations).** Its errors were scripted for eight participants across 24 recipes, so the 31% misordering / 42% parameter-deviation mix reflects the authors' scripts, not natural error rates. Use 4b or 4c as a counterweight.
2. **Co-tagging inflates counts.** In CaptainCook4D, 532 of 1,964 error steps carry two or more tags (e.g. Measurement and Order on the same step), so 2,574 tags describe about 1,964 erroneous steps. EPIC-Tent has 2 secondary labels. Pool percentages are shares of *tags*, not of erroneous steps.
3. **Unit mismatch.** CaptainCook4D and EgoPER count per step; Assembly101 (Ding) counts per attach/detach segment; EPIC-Tent counts per annotated interval; HoloAssist counts per fine-grained action; ATA counts per video. A repeated omission (EgoPER: five missing toothpicks = five errors) is counted differently across sets.
4. **Coverage gaps, not zeros.** Addition is annotated only in Assembly101 (as unnecessary detach), EgoPER (no counts) and ATA (figure only); repetition only in EPIC-Tent (3); early termination nowhere. Corrections are unannotated in CaptainCook4D and IndustReal. The pooled 0% for early termination and 0.1% for repetition are absence of labels.
5. **Ambiguous mappings** (flagged in Section 2): EgoPER Modification (WT vs PD), EPIC-Tent misuse (PD vs WT), EgoOops Incorrect-object-picking (WT vs AD), EgoOops Accidental-mistakes (UN vs AD), Assembly101 accumulated (UN). Moving EPIC-Tent misuse to WT would shift the mapped pool to WT 15.4% / PD 31.4%.
6. **Two Assembly101 snapshots disagree** (Table 1: 726 mistakes / 348 corrections; released CSVs: 707 / 330). Table 1 is used in the pool.
7. **Tallied numbers are not published numbers.** HoloAssist per-category counts, CaptainCook4D `Other`, EPIC-Tent per-type counts and the EgoOops reproduction were computed here from the official annotation files; HoloAssist covers train+val only (1,758 of 2,221 sessions).
8. **Double counting across benchmarks.** EgoErrorVQA, ProMQA, ProMQA-Assembly, PREGO's Assembly101-O / EPIC-Tent-O and Ding's Assembly101 labels all re-use CaptainCook4D, Assembly101 or EPIC-Tent footage; only one source per underlying dataset is pooled.
9. **Label validity.** PIE-V's audit found only 51% (EgoPER) to 74% (CaptainCook4D) of sampled annotated mistakes to be outcome-changing errors, so a share of the pooled labels are permissible variants.
10. **Robot data are a different population.** REFLECT's failures were injected or teleoperated in simulation/toy kitchens; ViFailback and RoboMIND policy-rollout shares describe controller failures (pose, gripper state), which have no counterpart in the human taxonomy. They are reported separately and not pooled.
11. **Not downloadable without a request:** EgoPER (email, two-week link, no license), ATA (university email), BRIO-TA (email), Assembly101 videos (gated Hugging Face, 3.89 TB), RoboMIND (gated). Publicly downloadable annotation files: CaptainCook4D, HoloAssist, IndustReal, Assembly101 mistake CSVs, EgoOops, EPIC-Tent, EgoErrorVQA QA JSON.

