# Relevance worksheet — twenty minutes, thirty postings

> Fill in `services/api/tests/fixtures/relevance/ratings.yaml`.
> This is QUESTIONS Q5. It is the only thing in this project that can measure
> whether the ranking is any *good*, as opposed to merely stable.

## What to do

**First, the profile block at the top of the file — once, about two minutes.**
Every rating below is a judgement made by a particular person, and without this
block M3d cannot tell a ranking that is wrong from a ranking that was scored
against an empty profile.

```yaml
rated_on: 2026-08-09           # today
profile:
  graduation: 2027-05          # year and month, or `not_stated`
  degree: bachelors            # none / bachelors / masters / phd
  years_experience: 1          # a whole number, internships included
  skills: [Python, TypeScript] # names from data/skills.yaml where they exist
  preferred_roles: [backend engineer, data engineer]
  preferred_locations: [New York, remote]
```

Nothing here is inferred from anything and nothing is copied out of the app —
invariant I2 means a qualification comes from you or it does not exist. If a
field does not apply, write `not_stated` rather than a plausible number.

**Then rate the thirty postings — one word each.**

| Rating | Means |
|---|---|
| `good` | You would open this and consider applying |
| `acceptable` | You would not be annoyed to see it in a list |
| `poor` | Wrong role, wrong level, or not for you |

Rate on **fit, not on your odds.** A role you would love and are underqualified
for is `good`. Whether you *can* apply is the eligibility gate's question, it is
already answered separately, and `matching.md` §5.2 forbids it from ever
becoming points — so answering it here would be measuring the wrong thing twice.

The ratings file lists the same thirty postings **in this order**, each with an
`n` matching the number below, so the two can be worked through side by side:

```yaml
- n: 1
  board: akunacapital_eligibility
  id: '8018880'
  title: Hardware Engineer Intern, Summer 2027
  rating: good        # <- the only line you change
  note: ''
```

`note` is optional and exists only for the ones that were hard to call. Skip it.

**Do not tie-break, do not rank, do not agonise.** Forty seconds each. A first
reaction is the thing being measured; a considered second opinion is not what
the ranked list will be judged against by a person scrolling it.

The excerpt under each posting is short on purpose — it is the requirements
section, cut at 600 characters. If it says `[no requirements heading found]` the
tool could not locate one, and you are looking at a guess: rate from the title
or skip it with a note.

---

## [1] akunacapital — Hardware Engineer Intern, Summer 2027

`akunacapital_eligibility` / `8018880`

> Requirements for this role: Pursuing a bachelor’s, master’s, or Ph.D. in Computer and Electrical Engineering, Computer Science, or a related field Graduating by August 2029 GPA of 3.5 or above Legal authorization to work in the U.S. is required on the first day of employment including F-1 students using CPT, OPT or STEM Previous experience in finance or trading is not required. Many of our engineers joined Akuna with little-to-no prior knowledge of the markets, and we pride ourselves on our ability to onboard those new to the industry. Training and continuous education are provided for all eng […cut off — open the fixture for the rest]

## [2] akunacapital — Broker Trader

`akunacapital_eligibility` / `7496423`

> Qualities that make great candidates: 2+ years of options market making experience Entrepreneurial self-starter ready to work in a fast paced, team environment Strong mathematical aptitude giving the ability to maximize trading opportunities in a high-pressure environment Effective and efficient communication and superior interpersonal skills Capable of developing and maintaining strong working business relationships Ability to work alongside and communicate with screen traders Passion for problem-solving and finding creative solutions in an ever-changing market VBA or Python programming skill […cut off — open the fixture for the rest]

## [3] anthropic — AI Compliance Officer

`anthropic_eligibility` / `5208218008`

> Minimum qualifications Experience building or running a compliance program in a regulated industry (e.g., technology, financial services or fintech, medical devices, data protection, or telecoms) Hands-on experience operationalizing a complex regulatory regime end-to-end, including translating legal requirements into controls, documentation, training, and reporting Demonstrated ability to work effectively in genuine ambiguity: novel regulation, evolving regulator expectations, and a fast-moving product environment Experience engaging directly with regulators and building trusted relationships  […cut off — open the fixture for the rest]

## [4] anthropic — Anthropic Fellows Program

`anthropic_eligibility` / `5023394008`

> you may be a good fit if you: Are motivated by making sure AI is safe and beneficial for society as a whole Are excited to transition into empirical AI research and would be interested in a full-time role at Anthropic Have a strong technical background in computer science, mathematics, or physics Thrive in fast-paced, collaborative environments Can implement ideas quickly and communicate clearly Strong candidates may also have: Strong background in a discipline relevant to a specific Fellows workstream (e.g. economics, social sciences, or cybersecurity) Experience in areas of research or engin […cut off — open the fixture for the rest]

## [5] anthropic — Anthropic Fellows Program, AI Safety

`anthropic_eligibility` / `5183044008`

> you may be a good fit if you: Are motivated by making sure AI is safe and beneficial for society as a whole Are excited to transition into empirical AI research and would be interested in a full-time role at Anthropic Have a strong technical background in computer science, mathematics, or physics Thrive in fast-paced, collaborative environments Can implement ideas quickly and communicate clearly Strong candidates may also have: Strong background in a discipline relevant to a specific Fellows workstream (e.g. economics, social sciences, or cybersecurity) Experience in areas of research or engin […cut off — open the fixture for the rest]

## [6] anthropic — Applied AI Architect

`anthropic_eligibility` / `5076109008`

> You may be a good fit if you have: 5+ years of experience in technical customer-facing roles such as Solutions Architect, Sales Engineer, or Technical Account Manager Native-level Japanese fluency and business-level English required Experience working with enterprise customers, navigating complex buying cycles involving multiple stakeholders Exceptional ability to build relationships with and communicate technical concepts to diverse stakeholders to include C-suite executives, engineering & IT teams, and more Strong technical communication skills with the ability to translate customer requirem […cut off — open the fixture for the rest]

## [7] databricks — Account Executive 

`databricks_eligibility` / `6918763002`

> What we look for: You have previously worked in an early-stage company and you know how to navigate and be successful in a fast-growing organisation 5+ years of sales experience in SaaS/PaaS, or Big Data companies Prior customer relationships with CIOs and important decision-makers Simply articulate intricate cloud technologies and big data 3+ years of experience exceeding sales quotas Success closing new accounts while upselling existing accounts Bachelor's Degree About Databricks Databricks is the data and AI company. More than 10,000 organizations worldwide — including Comcast, Condé Nast,  […cut off — open the fixture for the rest]

## [8] databricks — Customer Enablement Specialist

`databricks_eligibility` / `8431935002`

> Bonus Points Databricks certifications or willingness to certify (Data Engineer Associate, Databricks certifications (or willingness to obtain within 6 months). Background in SaaS, cloud, or data platforms; familiarity with BI or AI/BI tools (Databricks Genie, Tableau, Power BI). Exposure to Databricks Apps, REST APIs, or AI agent concepts. Experience in a role with enablement or training-related revenue metrics. Why This Role, Why Now New products create new skill gaps. As Databricks expands into AI/BI, Databricks Apps, and agent-based development, a new wave of users — business analysts, app […cut off — open the fixture for the rest]

## [9] databricks — Associate Product Manager, New Grad (2027 Start)

`databricks_eligibility` / `7586263002`

> What we look for: You will graduate in Fall 2026 or Spring 2027 with a bachelors or masters degree in computer science or related engineering practice Pursuing a bachelor's or master's in computer science or a related engineering field You've used AI tooling for both personal productivity and development projects You have some first hand experience with SQL and/or Python You're hands-on and learn by doing — happy to build, test, and iterate your way to an answer You use analytical skills to make data-driven decisions (e.g. analyzing product usage) You can make complex topics simple and communi […cut off — open the fixture for the rest]

## [10] databricks — AI Engineer - FDE (Forward Deployed Engineer)

`databricks_eligibility` / `8099751002`

> What we look for: Experience building GenAI applications, including RAG, multi-agent systems, Text2SQL, fine-tuning, etc., with tools such as HuggingFace, LangChain, and DSPy Expertise in deploying production-grade GenAI applications, including evaluation and optimizations Extensive years of hands-on industry data science experience, leveraging common machine learning and data science tools, i.e. pandas, scikit-learn, PyTorch, etc. Experience building production-grade machine learning deployments on AWS, Azure, or GCP Graduate degree in a quantitative discipline (Computer Science, Engineering, […cut off — open the fixture for the rest]

## [11] imc — AML/KYC Officer (Crypto)

`imc_eligibility` / `4895334101`

> Your Skills and Experience: 4+ years of AML/KYC/CDD experience within crypto, trading, banking, payment institutions or other regulated financial institutions Strong understanding of enhanced due diligence (EDD) requirements and risk-based AML/KYC assessments Prior familiarity with AML/CTF risks and typologies relevant to digital assets and crypto markets is preferred (but not mandatory) Experience conducting independent risk assessments and exercising sound judgement Familiarity with crypto transaction tracing and wallet screening tools is preferred Knowledge of relevant AML/CTF legislation,  […cut off — open the fixture for the rest]

## [12] imc — Corporate Development Manager

`imc_eligibility` / `4805270101`

> Your Skills and Experience: 8+ years of experience in Indian financial markets, specifically in one or more of the following: business development at an exchange (NSE, BSE, MCX), institutional/FPI brokerage (exchange relations or operations), or financial markets regulatory consulting Direct working experience with NSE and/or BSE in a professional capacity (as an exchange employee or broker exchange relations manager) Strong working knowledge of proprietary trading firms and HFT/market-making firms: must already know the relevant issues, have the judgment to assess what is and is not relevant  […cut off — open the fixture for the rest]

## [13] imc —  Graduate Machine Learning Researcher - London

`imc_eligibility` / `4914883101`

> Your Skills and Experience: Currently in your final year of study, graduating in 2027 A minimum of an MSc (PhD preferred) in Machine Learning, Statistics, Deep Learning, Probabilistic Programming, or a related quantitative field Strong foundations in statistics and machine learning, with a demonstrated research track record in ML, deep learning, or another quantitative field Proficiency in fundamental ML frameworks like Pytorch and experience in Python Solid understanding of statistics Desirable: publications in respected journals covering deep learning or time-series modeling No prior finance […cut off — open the fixture for the rest]

## [14] imc — Commodities Broker Trader 

`imc_eligibility` / `4658374101`

> Your skills and experience: 2+ years of experience as an Execution/Broker Trader BS, MS preferably in business, economics or STEM You have a quantitative and strategic mindset and a healthy appetite for risk Strong technical skills in Statistics and Python You have a proven ability to act and make decisions in a fast-paced and competitive environment You are analytical, passionate about reflecting on past trades, and always seeking to do better Strong communication and teamwork abilities About Us IMC is a global trading firm powered by a cutting-edge research environment and a world-class tech […cut off — open the fixture for the rest]

## [15] janestreet — Campus Recruiter

`janestreet_eligibility` / `8469230002`

> About You Have 8+ years of university recruiting experience (no financial industry experience required) Eager to learn new skills and make an immediate impact Creative thinker with a deep understanding of the candidate landscape; able to help us anticipate where we need to go next to find great hires Self-starter who can prioritise tasks, stay organised and turn ideas into action Flexible team player with a roll-up-your-sleeves, no-job-too-small attitude Able to communicate clearly with colleagues, candidates and external partners Approachable and humble about what you know and don’t know; not […cut off — open the fixture for the rest]

## [16] jumptrading — Campus AI Research Engineer (Full-Time)

`jumptrading_eligibility` / `8052313`

> Skills You'll Need: This role covers a wide range of potential projects and skills. We don't expect everyone to have all of these, but for the applicable areas we are looking for deep technical expertise. Creative thinkers who are driven, self-motivated, and eager to solve challenging problems Proficiency in Python and/or C++ Proficiency in PyTorch, JAX, TensorFlow, and/or similar frameworks Ability to thrive in a collaborative, team-oriented environment Expertise in GPU or accelerator programming (CUDA, Triton, SYCL, ROCm, or equivalent) Experience building AI/ML systems at scale (hundreds of […cut off — open the fixture for the rest]

## [17] janestreet — ASIC Engineer

`janestreet_eligibility` / `8213653002`

> About You Have 4+ years practical experience in RTL design and verification Experienced in ASIC design using either Synopsys or Cadence flows, including at least one of the following: Front-end RTL design and synthesis Back-end physical design Verification (including formal) Interested in using software engineering techniques to improve the hardware design process, and experience programming in some high-level languages (Python, C++, Java, Haskell, etc.) If you're a recruiting agency and want to partner with us, please reach out to agency-partnerships@janestreet.com .

## [18] jumptrading — Accounting Manager | Finance 

`jumptrading_eligibility` / `8071050`

> Skills You'll Need: Qualified accountant (ACA, ACCA, CPA or equivalent) with 5+ years of relevant post-qualification experience Strong statutory accounting background with hands-on experience owning multiple legal entities, ideally across more than one European jurisdiction Familiarity with European local-GAAP reporting; experience with German HGB is a distinct advantage Experience with a major ERP and strong Excel; comfort adopting new technology and automation tools Proven experience managing external audits and partnering with third-party accountants Reliable and predictable availability 

## [19] oldmissioncapital — Software Engineer – 2027 Internship Program (June Start)

`oldmissioncapital_eligibility` / `7796180003`

> [no requirements heading found — showing the end of the posting] ess to people across the firm — traders, researchers, and engineers Base Salary Range $150,000 - $200,000 - Salaries are based on numerous factors such as skills, experience, and education. For more information, reach out to your recruiter. Old Mission is not accepting unsolicited resumes from any staffing/search firms. All resumes submitted by staffing/search firms to any employee at Old Mission via-email, the Internet or directly without a valid signed search agreement will be deemed the sole property of Old Mission, and no fee will be paid in the event the candidate is hired by Old Mission.

## [20] jumptrading — AI Research Scientist | Research & Development

`jumptrading_eligibility` / `4982814`

> preferred), TensorFlow, and/or JAX Intellectual curiosity, versatility, and originality combined with a pragmatic outlook Ability to reason through quantitative problems and communicate effectively with trading researchers PhD, or Master's degree in Computer Science, Mathematics, (or related subject) Strong publications record at ICML, ICLR, AAAI, NeurIPS, UAI, KDD, or equivalent Reliable and predictable availability Bonus Points Experience with HPC and distributed large model training Experience with GPU performance optimization (CUDA or ROCm) Experience with end-to-end model development, esp […cut off — open the fixture for the rest]

## [21] oldmissioncapital — Employee Experience Specialist (Receptionist)

`oldmissioncapital_eligibility` / `7790670003`

> The ideal candidate is dependable, detail-oriented, and takes pride in keeping things running smoothly behind the scenes. What You'll Do Front Desk & Visitor Experience Greet visitors warmly and ensure a polished first impression of Old Mission Answer and direct incoming phone calls professionally Manage incoming and outgoing mail, deliveries, shipments, adhering to compliance requirements where needed Track guests in building registration software and on internal calendars Facilitate daily lunch offering to in-office employees, ensuring timely delivery and troubleshooting issues Coordinate se […cut off — open the fixture for the rest]

## [22] point72 — Fundamental Research Fellow, Canvas 

`point72_eligibility` / `8492784002`

> REQUIRED Undergraduate degree conferred in 2025 or 2026 Strong analytical skills Excellent written and verbal communication abilities An eagerness to find out if your conclusions are right or wrong An understanding of how companies work (their processes and outcomes) or an interest in learning Intellectual curiosity, creative thinking, maturity Highest standards of ethical decision making WHAT SUCCESS LOOKS LIKE Integrity – You demonstrate 100% commitment to the highest ethical standards Ownership – You take charge of your work, uphold your commitments, and always do your best Commerciality –  […cut off — open the fixture for the rest]

## [23] oldmissioncapital — C++ Software Engineer

`oldmissioncapital_eligibility` / `6515984003`

> Required Skills BS/BA degree in Computer Science, Engineering, or another technical related field 7+ years of experience developing applications in modern C++ Experience with C++ 11/14/17/20, Linux and Python and BASH scripting In-depth knowledge of the Linux kernel, systems programming A passion for solving challenging problems Strong systems knowledge and prefer some experience in developing low latency systems Experience with writing applications connecting to exchange API’s or using network protocols Experience with parallel, concurrent, and multi-threaded programming Prefer experience wit […cut off — open the fixture for the rest]

## [24] akunacapital — Platform Engineer Intern, Summer 2027

`akunacapital_eligibility` / `8018856`

> Requirements for this role: Pursuing a bachelor’s, master’s, or Ph.D. in a technical field (computer science/engineering, math, physics, or equivalent) Graduating by August 2028 Major GPA of 3.5 or above Legal authorization to work in the U.S. is required on the first day of employment including F-1 students using OPT or STEM Previous experience in finance or trading is not required. Many of our engineers joined Akuna with little-to-no prior knowledge of the markets, and we pride ourselves on our ability to onboard those new to the industry. Training and continuous education are provided for a […cut off — open the fixture for the rest]

## [25] openai — Security Engineer, Application Security

`openai_eligibility` / `0322d6d8-6588-4209-a304-83e768063a25`

> You might thrive in this role if you: - Extensive experience in information security, cybersecurity, or a related field, with a significant portion of that experience in leadership or management roles. - Deep understanding of security technologies, tools, and best practices, including experience with secure coding practices, threat modeling, risk assessments, and incident response. - Experience in application security, software development, or related areas with a strong understanding of secure coding practices and application security frameworks. - Proficiency in programming languages (such a […cut off — open the fixture for the rest]

## [26] databricks — PhD GenAI Research Scientist Intern

`databricks_eligibility` / `7011263002`

> qualifications and qualities: Required: Research experience in and proficiency with the fundamentals of deep learning. Pursuing a PhD in computer science or related fields (electrical engineering, neuroscience, physics, math, etc.). Proficient software engineering skills, including with PyTorch. Pay Range Transparency Databricks is committed to fair and equitable compensation practices. 

## [27] point72 — AI Data Scientist

`point72_eligibility` / `8658618002`

> REQUIREMENTS PhD in Computer Science, with a specialization in AI or machine learning related domains Strong programming skills in Python and SQL Strong publication record in top tier machine learning conferences 3+ years of experience as a Data Scientist or similar role Experience working with large data sets including predictive modeling Financial industry experience preferred but not required Strong organization, communication and interpersonal skills Intellectual curiosity and enthusiasm for learning Attention to detail and a love of processes Strong oral and written communication skills A […cut off — open the fixture for the rest]

## [28] imc — Graduate Hardware Engineer

`imc_eligibility` / `4823805101`

> Your Skills and Experience: Current university student graduating between September 2026 – July 2027 that is pursuing a degree in Electrical Engineering, Computer Engineering, or a related degree Strong analytical skills and a desire to solve complex problems programmatically Proficient in SystemVerilog, Verilog, VHDL, or other RTL programming (additional software experience is a plus; C++, Python, or similar) Desire to collaborate with non-engineers in a dynamic environment Interest in the Financial Markets; previous knowledge is NOT required Must be available for full-time employment startin […cut off — open the fixture for the rest]

## [29] jumptrading — Campus AI Research Engineer - Deep Learning (Intern)

`jumptrading_eligibility` / `8052338`

> Skills You'll Need: Strong publication record at ICML, ICLR, AAAI, NeurIPS, UAI, KDD, or equivalent and/or contributions to open-source AI research Strong general ML background with exposure to modern deep learning techniques and/or language modeling architectures (e.g. transformers, SSMs) Solid development skills in Python and/or C++ Familiarity with ML libraries/frameworks such as PyTorch, JAX, and/or TensorFlow Intellectual curiosity, versatility, and originality combined with a pragmatic outlook Ability to thrive in a collaborative, team-oriented environment Ability to reason through quant […cut off — open the fixture for the rest]

## [30] point72 — 2026 Warsaw MI Data – Web Scraping Internship 

`point72_eligibility` / `8423978002`

> [no requirements heading found — showing the end of the posting] through fundamental and systematic investing strategies across asset classes and geographies. We aim to attract and retain the industry’s brightest talent by cultivating an investor‑led culture and committing to our people’s long‑term growth. For more information, visit https://point72.com/ . Our Warsaw office gives us access to world‑class talent with a reputation for excellence and innovation. We’re looking to build an office of subject‑matter experts whose fresh perspectives will help evolve our infrastructure and advance the capabilities of our teams. Learn more at Warsaw Office – Point72.
