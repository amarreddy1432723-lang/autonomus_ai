/**
 * Universal Interview LLM & Fallback Engine
 * Supports:
 *  1. Direct User API Keys (Groq, OpenAI, Google Gemini, OpenRouter, Anthropic)
 *  2. Arceus Backend Agent Stream (/api/v1/agents/chat)
 *  3. Instant Context-Aware Smart Fallback Generator (100% offline & login-free)
 */

export type ProviderKeyConfig = {
  provider: 'groq' | 'openai' | 'gemini' | 'openrouter' | 'anthropic' | 'arceus_backend';
  apiKey?: string;
  customModel?: string;
};

const STORAGE_KEY = 'arceus_interview_api_keys';

export function getStoredApiKeys(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function saveApiKey(provider: string, key: string) {
  if (typeof window === 'undefined') return;
  try {
    const existing = getStoredApiKeys();
    if (key.trim()) {
      existing[provider] = key.trim();
    } else {
      delete existing[provider];
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
  } catch (err) {
    console.error('Failed to save API key:', err);
  }
}

export function getActiveProvider(): { provider: string; key: string } {
  const keys = getStoredApiKeys();
  if (keys.groq) return { provider: 'groq', key: keys.groq };
  if (keys.openai) return { provider: 'openai', key: keys.openai };
  if (keys.gemini) return { provider: 'gemini', key: keys.gemini };
  if (keys.openrouter) return { provider: 'openrouter', key: keys.openrouter };
  return { provider: 'arceus_backend', key: '' };
}

export function autoCorrectInterviewInput(raw: string): string {
  if (!raw || typeof raw !== 'string') return '';
  let text = raw.trim();

  const replacements: Array<[RegExp, string]> = [
    // Apprenticeship / Program
    [/\b(friendship|apprentis|apprentiship|apprentice ship)\b/gi, 'apprenticeship'],
    [/\b(google apprentice|google apprentices)\b/gi, 'Google Apprenticeship'],

    // Coding / Reversing strings / Algorithms
    [/\b(reversities string|reversities|code of river|river system|revert a string|reverse of string|river string|revers string)\b/gi, 'reverse a string'],
    [/\b(two sum|to sum|too sum)\b/gi, 'Two Sum'],
    [/\b(palindrom|palin drome)\b/gi, 'palindrome'],
    [/\b(fizz buzz|fiz buz)\b/gi, 'FizzBuzz'],
    [/\b(linked list|link list|linklist)\b/gi, 'linked list'],
    [/\b(binary search|binery search)\b/gi, 'binary search'],

    // Projects / Hackathons
    [/\b(tata steel hacker|tata steel hack)\b/gi, 'Tata Steel Hackathon'],
    [/\b(hacker\s+and\s+arctic)\b/gi, 'hackathon and architect'],
    [/\b(arctic|artick|artic)\s+relational\b/gi, 'architect relational'],
    [/\b(sobu|so buh|local adda|localadda)\b/gi, 'SOBUH'],
    [/\b(maintenance wizard|maintanance wizard)\b/gi, 'Maintenance Wizard'],

    // Analytics / Metrics
    [/\b(rock oak|rock auc|raw cuck|roc auc|auc roc)\b/gi, 'ROC-AUC'],
    [/\b(sequel|cquel|s q l)\b/gi, 'SQL'],
    [/\b(pythan|pythn)\b/gi, 'Python'],
    [/\b(pan does|pan das)\b/gi, 'Pandas'],
    [/\b(num pie|num py)\b/gi, 'NumPy'],
    [/\b(psycit learn|cycle learn|scikit)\b/gi, 'Scikit-Learn'],
    [/\b(eda|e d a)\b/gi, 'EDA (Exploratory Data Analysis)'],
    [/\b(imbalance data|unbalance dataset|imbalanced data)\b/gi, 'imbalanced dataset'],
    [/\b(null values|missing values|missing data)\b/gi, 'missing values'],
  ];

  for (const [pattern, replacement] of replacements) {
    text = text.replace(pattern, replacement);
  }

  return text;
}

export type InterviewStreamOptions = {
  question: string;
  resumeText?: string;
  targetRole?: string;
  targetCompany?: string;
  jobDescription?: string;
  projectNotes?: string;
  interviewPrompt?: string;
  interviewStyle?: string;
  onToken: (token: string, accumulated: string) => void;
  signal?: AbortSignal;
};

export function buildSystemPrompt(options: InterviewStreamOptions): string {
  const { resumeText, targetRole, targetCompany, jobDescription, projectNotes, interviewPrompt, interviewStyle = 'short' } = options;

  const isGoogle = targetCompany?.toLowerCase().includes('google') || targetCompany?.toLowerCase().includes('alphabet');

  let styleDesc = '';
  if (interviewStyle === 'technical') {
    styleDesc = 'Expert technical answer. Start with the core concept, then go as deep as needed — internals, trade-offs, complexity, edge cases, real implementation. Use code blocks when it helps. No word limit.';
  } else if (interviewStyle === 'star') {
    styleDesc = 'STAR method — natural, not formulaic. Situation → Task → specific Actions with real technical decisions → measurable Result. Include what you learned. Cover it fully.';
  } else if (interviewStyle === 'fresher') {
    styleDesc = 'Sharp, curious, eager. Strong fundamentals, academic/personal projects, fast learning, collaborative ownership. Show growth mindset. Cover it fully — do not cut short.';
  } else if (interviewStyle === 'confident') {
    styleDesc = 'Senior engineer conviction. Deep ownership, architectural thinking, cross-functional impact, quantified outcomes. Lead with the result, explain how, be specific.';
  } else if (interviewStyle === 'short') {
    styleDesc = 'Spoken-ready natural English. Warm and confident — not rehearsed. Go straight to your answer. Aim for 60-90 seconds of speaking. No padding.';
  } else {
    styleDesc = 'Natural, confident, first-person. Answer completely and specifically. Cover the question fully with real examples and specific details.';
  }

  return `You are a world-class AI interview coach AND personal assistant for ${targetRole || 'a job candidate'}${isGoogle ? ' applying for a Google Apprenticeship' : targetCompany ? ` at ${targetCompany}` : ''}.

## YOUR ROLE
You answer ANY question the user asks — interview questions, technical questions, coding problems, general knowledge, life advice, or anything else. Always use the candidate's profile/resume data to personalize answers when relevant.

## CORE RULES
1. Answer in first person ("I", "my team", "we built") for interview questions — you ARE the candidate speaking.
2. For technical/coding questions: give the full correct answer with examples and code if needed.
3. For general questions: answer directly, helpfully, accurately.
4. NEVER say "As an AI", "Great question", "Here is an answer" — just answer.
5. Sound like a real, smart, confident human. Natural contractions, no robotic stiffness.
6. Style: ${styleDesc}

${isGoogle ? `## GOOGLE APPRENTICESHIP STANDARDS
- Googleyness: Show intellectual curiosity, collaboration, ethical thinking
- Technical Excellence: Edge cases, scale, clean code, system thinking  
- Impact at Scale: Measurable outcomes, think big
- End behavioral answers with what you LEARNED or how it changed you` : ''}

${targetRole ? `## TARGET ROLE: ${targetRole}` : ''}
${targetCompany ? `## TARGET COMPANY: ${targetCompany}` : ''}

${jobDescription ? `## JOB DESCRIPTION (tailor every interview answer to this):
${jobDescription.slice(0, 2000)}` : ''}

${resumeText ? `## CANDIDATE MASTER PROFILE & RESUME (Use this comprehensive data to ground EVERY personal answer — reference real projects like Tata Steel Maintenance Wizard, SOBUH, skills, metrics, and reasoning):
${resumeText.slice(0, 25000)}` : '## NOTE: No profile data provided yet — give strong general answers and suggest the user add their profile in settings.'}

## ANSWER QUALITY
- Behavioral/HR: STAR format naturally + quantified result + lesson learned — full answer, don't cut short
- Technical/Coding: Concept → full implementation → trade-offs → code blocks freely
- "Tell me about yourself": Full professional arc — background (CSE, 8.19 CGPA) → real projects (Tata Steel industrial analytics, SOBUH SQL/business platform, applied AI) → why Google Data Analytics Apprenticeship
- "Why Google Apprenticeship": Bridge narrative — strong foundation in projects/hackathons seeking professional industry experience with real business datasets and experienced teams at Google's scale
- "Metrics/Projects": Mention ROC-AUC, precision-recall for imbalanced data in Tata Steel; relational SQL design & business metrics in SOBUH
- Any question: Answer completely, specifically, and with 100% technical and contextual accuracy. NEVER truncate.
- NEVER recite raw contact info (email, phone, LinkedIn URL, address) in your answers — only use professional content from the profile.
- NEVER start an answer by repeating the person's name or contact details.
`;
}

/**
 * Direct call to OpenAI / Groq / OpenRouter / Gemini OpenAI-compatible endpoints
 */
async function streamFromOpenAiCompatible(
  endpoint: string,
  apiKey: string,
  model: string,
  messages: Array<{ role: string; content: string }>,
  onToken: (token: string, accumulated: string) => void,
  signal?: AbortSignal
): Promise<string> {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages,
      stream: true,
      temperature: 0.65,
    }),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    throw new Error(`LLM API returned ${response.status}: ${errorText || response.statusText}`);
  }

  if (!response.body) throw new Error('Response stream was empty');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith(':')) continue;
      if (trimmed === 'data: [DONE]') break;
      if (trimmed.startsWith('data: ')) {
        try {
          const json = JSON.parse(trimmed.slice(6));
          const delta = json.choices?.[0]?.delta?.content || '';
          if (delta) {
            accumulated += delta;
            onToken(delta, accumulated);
          }
        } catch {
          // ignore stream parse errors
        }
      }
    }
  }

  return accumulated;
}

/**
 * Direct call to Google Gemini Native API
 */
async function streamFromGemini(
  apiKey: string,
  model: string,
  systemPrompt: string,
  question: string,
  onToken: (token: string, accumulated: string) => void,
  signal?: AbortSignal
): Promise<string> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?key=${apiKey}&alt=sse`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [
        {
          role: 'user',
          parts: [{ text: `${systemPrompt}\n\nInterviewer Question: "${question}"\n\nPlease answer now:` }],
        },
      ],
    }),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    throw new Error(`Gemini API error: ${errorText || response.statusText}`);
  }

  if (!response.body) throw new Error('Gemini response body empty');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        try {
          const json = JSON.parse(trimmed.slice(6));
          const text = json.candidates?.[0]?.content?.parts?.[0]?.text || '';
          if (text) {
            accumulated += text;
            onToken(text, accumulated);
          }
        } catch {
          // parse error
        }
      }
    }
  }

  return accumulated;
}

/**
 * Smart Instant Generative Synthesizer (Profile-Aware Intelligent Synthesizer)
 */
async function streamSmartFallback(
  options: InterviewStreamOptions,
  onToken: (token: string, accumulated: string) => void,
  signal?: AbortSignal
): Promise<string> {
  const rawPrompt = options.question;
  const actualQMatch = rawPrompt.match(/Now answer this question:\s*([\s\S]+?)$/i);
  const actualQ = actualQMatch ? actualQMatch[1].trim() : (rawPrompt.split('\n').pop()?.trim() || rawPrompt);
  const q = actualQ.toLowerCase().replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();

  const role = options.targetRole || 'Data Analytics Apprentice';
  const company = options.targetCompany || 'Google';
  const isGoogle = company.toLowerCase().includes('google') || q.includes('google');

  const profile = options.resumeText || '';
  const isDataAnalyticsProfile = profile.toLowerCase().includes('data analytics') || profile.toLowerCase().includes('tata steel') || profile.toLowerCase().includes('sobuh');

  let generatedText = '';

  // ── Greetings & Ice Breakers ─────────────────────────────────────
  if (
    q === 'hi' || q === 'hello' || q === 'hi hello' || q === 'hey' || q === 'good morning' ||
    q === 'good afternoon' || q === 'good evening' || q === 'how are you' || q.startsWith('hello') ||
    q.startsWith('hi ') || q === 'hey there' || q.includes('nice to meet you')
  ) {
    generatedText = `Hello! Thank you for having me today. I'm really excited to be speaking with you and discussing how my background in data analytics and software development connects with the ${role} role at ${company}. Whenever you're ready, I'm happy to dive in!`;
  }
  // ── Incomplete or Fragmented Transcripts ─────────────────────────
  else if (q === 'what do you understand from the' || q === 'what do you understand from' || q === 'what do you understand') {
    generatedText = `Data Analytics is the process of examining, cleaning, transforming, and modeling data to discover actionable insights and drive informed business decisions.\n\nIt consists of four main pillars:\n1. **Descriptive Analytics**: Examining historical data to understand *what happened* (e.g., summary metrics, dashboards, transaction counts in SOBUH).\n2. **Diagnostic Analytics**: Drilling down to understand *why it happened* (e.g., investigating why sensor anomalies spiked in the Tata Steel dataset).\n3. **Predictive Analytics**: Using statistical techniques and machine learning to forecast *what will happen* (e.g., predicting equipment failure risks using ROC-AUC evaluation).\n4. **Prescriptive Analytics**: Recommending actions to take based on predicted outcomes (e.g., preventative maintenance schedules to reduce downtime).\n\nIn practice, 60–70% of the effort is spent on data validation and cleaning—because the quality of any analysis is directly bounded by the integrity of the underlying data.`;
  }
  // ── "Google apprentice program" / What is Google Apprenticeship ────
  else if (q === 'google apprentice program' || q === 'google apprenticeship program' || q.includes('what do you know about the apprenticeship') || q.includes('what is the apprenticeship') || q.includes('tell me about the google apprentice')) {
    generatedText = `The Google Apprenticeship Program is a dedicated, immersive pathway designed to bridge the gap between academic learning and real-world industry practice.\n\nIt provides aspiring engineers and analysts who already have a strong foundational skill set—such as Python, SQL, and exploratory data analysis—with the opportunity to work alongside experienced Google teams on live production systems and large-scale datasets.\n\nWhat makes it unique is the combination of structured on-the-job training, mentorship from senior engineers, and hands-on exposure to how data problems are framed, solved, and communicated at Google's global scale. It's designed to build well-rounded, production-ready professionals through real contribution and continuous learning.`;
  }
  // ── Why Google Apprenticeship / Why Suitable / Why Apply ───────────
  else if (
    q.includes('why') && (q.includes('apprentice') || q.includes('program') || q.includes('suitable') || q.includes('apply') || q.includes('join') || q.includes('why this') || q.includes('why google')) ||
    q.includes('why did you apply') || q.includes('why do you want this') || q.includes('why suitable for you')
  ) {
    if (isGoogle || isDataAnalyticsProfile) {
      generatedText = `I applied for the Google Data Analytics Apprenticeship because it provides the exact bridge I need between my academic and project-driven background and real-world professional practice.\n\nThrough my Computer Science degree and hackathon projects—like building failure prediction models in the Tata Steel AI Hackathon and architecting relational SQL databases for SOBUH—I've built a solid technical foundation in SQL, Python, data cleaning, and exploratory analysis. However, most of my experience has been self-driven and project-based.\n\nI want to work at Google because of the unmatched scale and complexity of the problems you solve, and how deeply data drives every product decision. The apprenticeship structure is ideal for me right now because I learn fastest in an environment where I can collaborate with experienced mentors, learn industry-standard analytical workflows, and understand how data translates into business impact at scale.\n\nI'm ready to contribute with my existing SQL and data skills from day one, while learning how world-class teams operate.`;
    } else {
      generatedText = `I applied because I have built a strong foundational skillset in software engineering and data analytics through hands-on projects, and I am now ready to transition that into professional industry experience.\n\nThe apprenticeship model appeals to me because it combines real-world project ownership with structured mentorship from experienced engineers. I learn best when applying my skills to production-level challenges, and I want to contribute to meaningful problems while leveling up my engineering rigor.`;
    }
  }
  // ── Tell Me About Yourself / Introduction ───────────────────────────
  else if (q.includes('tell me about yourself') || q.includes('introduce yourself') || q.includes('walk me through your resume') || q.includes('who are you')) {
    if (isDataAnalyticsProfile) {
      generatedText = `I'm a Computer Science graduate graduating in 2026 with an 8.19 CGPA, with a strong focus on data analytics, SQL, and data-driven problem solving.\n\nOver the past couple of years, I've focused on applying analytical and programming skills to real-world datasets across multiple projects:\n\n- In the **Tata Steel AI Hackathon**, my team built **Maintenance Wizard**, an industrial analytics solution where I performed data cleaning, exploratory data analysis, and anomaly detection on equipment sensor telemetry. We evaluated models using ROC-AUC and precision-recall to identify failure risks on highly imbalanced datasets.\n- I also worked on **SOBUH** (previously LocalAdda), a multi-sided business platform where I designed relational database schemas in SQL (PostgreSQL/MySQL), wrote complex queries and aggregations, and created dashboards to monitor customer engagement, booking trends, and revenue metrics.\n- Additionally, I've explored applied AI through projects in Alzheimer's detection and automated content moderation.\n\nI'm now seeking to transition from project-driven work to professional industry experience through the Google Data Analytics Apprenticeship, where I can apply my SQL and analytical skills to solve complex problems at scale.`;
    } else {
      generatedText = `I'm a Software Engineer who loves building reliable, data-driven systems that solve real problems. Over the past couple of years, I've focused on full-stack engineering and data analysis—using React, Python, and SQL to ship products and extract actionable insights. What drives me is end-to-end ownership: understanding the problem deeply, writing clean code, and using data metrics to make informed engineering decisions. I'm excited about this opportunity because I want to bring that curiosity and technical rigor to problems that matter at scale.`;
    }
  }
  // ── Tata Steel / Maintenance Wizard / Anomaly Detection / Metric ────
  else if (q.includes('tata steel') || q.includes('maintenance wizard') || q.includes('which metric') || q.includes('metric did you use') || q.includes('imbalanced') || q.includes('anomaly')) {
    generatedText = `For the **Tata Steel Maintenance Wizard** project, we analyzed industrial equipment sensor telemetry to identify abnormal operating patterns and predict machine failure risks before breakdown.\n\nA key challenge was that equipment failures occur very rarely, making the dataset **heavily imbalanced** (less than 1–2% positive failure cases). Because of this:\n- **We avoided relying on simple Accuracy**, since a naive model predicting 'no failure' 100% of the time would achieve 98% accuracy while being completely useless in practice.\n- Instead, we used **ROC-AUC (Receiver Operating Characteristic - Area Under Curve)** as our primary metric to evaluate how effectively the model distinguished failure states from normal operations across all decision thresholds.\n- We also tracked **Precision, Recall, and F1-Score** (as well as PR-AUC), tuning the decision threshold to prioritize higher recall—ensuring critical failure signals weren't missed while keeping false alarms manageable for maintenance teams.`;
  }
  // ── SOBUH / LocalAdda / Database / Business Metrics ─────────────────
  else if (q.includes('sobuh') || q.includes('localadda') || q.includes('local adda') || q.includes('business platform') || q.includes('booking')) {
    generatedText = `I worked on **SOBUH** (which was previously developed under the name **LocalAdda**), a multi-sided platform connecting customers, creators, and local service providers.\n\nMy primary focus was on database architecture and business analytics:\n- **Database Design**: Structured relational schemas in SQL (PostgreSQL/MySQL) to manage entities like users, service bookings, orders, and payment transactions with appropriate foreign keys and indexes.\n- **SQL Queries & Aggregations**: Wrote SQL queries utilizing joins, subqueries, ` + '`GROUP BY`' + `, and window functions to aggregate transactional data.\n- **Business Intelligence & Dashboards**: Built KPI metrics tracking customer retention, active booking rates, order fulfillment statuses, and revenue breakdowns to help identify growth patterns and service bottlenecks.\n- **Data Consistency**: Implemented validation constraints to ensure complete, clean, and reliable transactional records across the platform.`;
  }
  // ── Other Projects: Alzheimer's / Content Moderation ────────────────
  else if (q.includes('alzheimer') || q.includes('nsfw') || q.includes('content moderation') || q.includes('other project')) {
    generatedText = `Beyond industrial and business analytics, I've worked on applied AI projects to solve specific domain challenges:\n\n1. **Alzheimer's Detection**: An applied machine learning project focused on analyzing medical imaging patterns to support early-stage classification and pattern detection.\n2. **Content Moderation (NSFW Detection)**: An automated image classification pipeline designed to filter out inappropriate content before it gets published on user-facing platforms, focusing on precision to avoid false flags.\n\nThese projects helped me understand how machine learning models behave in practical scenarios where data preparation, preprocessing, and model evaluation directly impact user trust and application safety.`;
  }
  // ── Google Products Used / Improvement Idea ─────────────────────────
  else if (q.includes('google product') || q.includes('which google product') || q.includes('products do you use') || q.includes('improve google') || q.includes('sheets')) {
    generatedText = `I actively use several Google products in my daily technical and academic workflow:\n- **Google Sheets & Workspace**: For organizing structured datasets, rapid exploratory calculations, pivot tables, and collaborative documentation.\n- **NotebookLM**: For synthesizing complex multi-source documentation and research notes quickly.\n- **Gemini**: For technical conceptualization, brainstorming, and code refactoring.\n- **Google Cloud Console**: For configuring API keys, authentication, and service credentials.\n\n**Product Improvement Idea for Google Sheets**:\nWhile Google Sheets is outstanding for collaboration, moving data between Sheets and external Business Intelligence tools (like Power BI or custom analytical pipelines) often involves repetitive manual exports or custom scripts. Introducing a more seamless, native two-way connector and automated schema sync between Google Sheets and standard BI/SQL warehouses would save significant manual export time, reduce data transfer errors, and make lightweight reporting much faster for analytics teams.`;
  }
  // ── Why Google? (Company Specific) ──────────────────────────────────
  else if (q.includes('why google') || q.includes('why this company') || q.includes('why work at google')) {
    generatedText = `I'm deeply interested in Google because of the **scale, complexity, and data-driven nature of the problems you solve**.\n\nGoogle products like Search, Maps, YouTube, and Workspace impact billions of users every single day. At that scale, decisions cannot be based on intuition—they require rigorous data cleaning, metric design, and statistical analysis. I want to build my career in an environment where engineering excellence and analytical rigor are the baseline standard, and where data insights directly translate into better experiences for people globally.`;
  }
  // ── Why Select You / Contribution / Fit ──────────────────────────────
  else if (q.includes('why should we hire you') || q.includes('why select you') || q.includes('how can you contribute') || q.includes('what makes you a good fit') || q.includes('why you')) {
    generatedText = `I can contribute from day one because I have a solid foundation in core analytics skills—**SQL (joins, aggregations, window functions), Python (Pandas, NumPy, Scikit-learn), data cleaning, and exploratory data analysis**—combined with hands-on experience in real projects.\n\nIn the Tata Steel AI Hackathon, I demonstrated how to clean telemetry data and apply appropriate evaluation metrics (ROC-AUC) to imbalanced datasets. In SOBUH, I designed relational databases and built SQL queries to track business KPIs.\n\nBeyond technical skills, I bring strong curiosity, high coachability, and a fast learning curve. I don't just write queries; I take ownership of understanding the business context behind the numbers and communicating insights clearly.`;
  }
  // ── Closing Question / Any Questions for Us ─────────────────────────
  else if (q.includes('any question') || q.includes('questions for me') || q.includes('ask anything') || q.includes('closing question')) {
    generatedText = `Yes, thank you! I would love to ask:\n\n**“In your experience, what usually differentiates apprentices who do exceptionally well and thrive in this program from those who struggle?”**\n\n*(Alternative follow-up: “What kinds of data analytics problems or projects do apprentices typically get to contribute to during the first few months?”)*`;
  }
  // ── Finding Duplicates in SQL ───────────────────────────────────────
  else if (q.includes('duplicate') && (q.includes('sql') || q.includes('table') || q.includes('query') || q.includes('find'))) {
    generatedText = `To find duplicate records in SQL based on specific columns, you use ` + '`GROUP BY`' + ` combined with a ` + '`HAVING`' + ` clause:\n\n` +
      '```sql\n-- 1. Identify duplicates and their occurrence count\nSELECT email, COUNT(*)\nFROM users\nGROUP BY email\nHAVING COUNT(*) > 1;\n```\n\n' +
      `If you need to view the full rows or delete duplicates while retaining one original row, you can use the ` + '`ROW_NUMBER()`' + ` window function:\n\n` +
      '```sql\n-- 2. Rank duplicate rows using ROW_NUMBER()\nWITH RankedUsers AS (\n  SELECT *,\n         ROW_NUMBER() OVER (PARTITION BY email ORDER BY id ASC) AS row_num\n  FROM users\n)\nSELECT * FROM RankedUsers WHERE row_num > 1; -- Shows duplicate rows\n```';
  }
  // ── Missing Data / Handling Nulls ────────────────────────────────────
  else if (q.includes('missing data') || q.includes('missing value') || q.includes('null value') || q.includes('imputation') || q.includes('handle missing')) {
    generatedText = `When handling missing data in an analytics pipeline, I follow a systematic approach:\n\n1. **Identify the Missingness Mechanism**:\n   - **MCAR** (Missing Completely at Random): Safe to drop if percentage is negligible (<2–3%).\n   - **MAR** (Missing at Random) or **MNAR** (Missing Not at Random): Dropping creates bias; imputation or feature flagging is required.\n\n2. **Strategy Selection**:\n   - **Numerical Features**: Median imputation (preferred when outliers are present) or Mean imputation for normal distributions. For time-series data, forward-fill (FFill) or linear interpolation.\n   - **Categorical Features**: Mode imputation or assigning a distinct category like 'Unknown' / 'Missing'.\n   - **High Missingness (>50–60%)**: Drop the column or create a binary indicator column (e.g., is_missing = 1/0) if the absence itself contains a business signal.\n\n3. **Validation**: Always verify summary statistics before and after imputation to ensure the data distribution has not been artificially skewed.`;
  }
  // ── SQL / Joins / Database Concepts ──────────────────────────────────
  else if (q.includes('join') || q.includes('sql') || q.includes('database') || q.includes('query')) {
    generatedText = `In SQL, joins allow you to combine rows from two or more tables based on a related column:\n\n- **INNER JOIN**: Returns records that have matching values in both tables.\n- **LEFT (OUTER) JOIN**: Returns all records from the left table, and the matched records from the right table (unmatched right rows become NULL).\n- **RIGHT (OUTER) JOIN**: Returns all records from the right table, and matched records from the left table.\n- **FULL (OUTER) JOIN**: Returns all records when there is a match in either left or right table.\n- **CROSS JOIN**: Produces the Cartesian product of both tables.\n\nFor performance optimization on large datasets, ensure join keys are indexed, filter unnecessary rows early using WHERE before joining, and select only needed columns rather than SELECT *.`;
  }
  // ── Handling Conflict / Teammate / Non-Technical Explanation ────────
  else if (q.includes('conflict') || q.includes('disagree') || q.includes('teammate') || q.includes('non technical') || q.includes('stakeholder')) {
    generatedText = `When communicating complex analysis to non-technical stakeholders or resolving team disagreements, my approach is centered on clarity and objective data:\n\n1. **Lead with the 'Why' and the Business Impact**: Non-technical partners care about outcomes—how does this reduce equipment downtime, improve retention, or save costs? I avoid jargon like ROC-AUC or loss functions and focus on actionable insights.\n2. **Use Intuitive Visualizations**: Replace raw tables with clear charts (e.g., trend lines, breakdown bar charts) that highlight the core takeaway in under 5 seconds.\n3. **Listen and Align on Objectives**: If there is disagreement on an approach, I focus on the shared goal, document assumptions, and test hypotheses with small data experiments rather than opinions.`;
  }
  // ── Coding: Reverse a String / River String / Reverse Problem ────
  else if (
    q.includes('revers') || q.includes('river') || q.includes('string reverse') ||
    q.includes('reverse a string') || q.includes('reversities')
  ) {
    generatedText = `To reverse a string in Python, here are the most clean and optimal approaches:\n\n` +
      '```python\n# Approach 1: Slicing (Most Pythonic - O(N) Time, O(1) Aux Space)\ndef reverse_string(s: str) -> str:\n    return s[::-1]\n\n# Approach 2: Two Pointers (In-place if list of characters - O(N) Time, O(1) Space)\ndef reverse_char_array(chars: list[str]) -> None:\n    left, right = 0, len(chars) - 1\n    while left < right:\n        chars[left], chars[right] = chars[right], chars[left]\n        left += 1\n        right -= 1\n```\n\n' +
      `In an interview, I typically explain the **Two Pointer** technique first to demonstrate understanding of memory and in-place mutation, and then mention Python's built-in slice notation \`s[::-1]\` for production conciseness.`;
  }
  // ── Coding: Two Sum / Algorithms / General Code ─────────────────────
  else if (q.includes('two sum') || q.includes('palindrome') || q.includes('binary search') || q.includes('write a code') || q.includes('can you code') || q.includes('coding')) {
    generatedText = `Here is how I'd solve this systematically in Python using a Hash Map for optimal **O(N) Time Complexity and O(N) Space Complexity**:\n\n` +
      '```python\ndef two_sum(nums: list[int], target: int) -> list[int]:\n    seen = {} # map value -> index\n    for i, num in enumerate(nums):\n        complement = target - num\n        if complement in seen:\n            return [seen[complement], i]\n        seen[num] = i\n    return []\n```\n\n' +
      `**Walkthrough**:\n1. We maintain a dictionary \`seen\` mapping each visited number to its index.\n2. For each number, we check if \`target - num\` is already in our dictionary in O(1) lookup time.\n3. This avoids the naive O(N²) nested loop approach and runs in a single pass.`;
  }
  // ── Weakness / Area of Growth ─────────────────────────────────────────
  else if (q.includes('weakness') || q.includes('improve') || q.includes('grow')) {
    generatedText = `Early on in my projects, I had a tendency to over-engineer solutions—spending excessive time building complex models or optimizing code before thoroughly validating if the baseline data answered the core question.\n\nI've addressed this by adopting a **hypothesis-driven, iterative workflow**: start with thorough exploratory data analysis (EDA), build a simple, working baseline model, validate the insights with the team, and only add complexity where the metrics prove it's necessary. This has made my problem-solving much faster and more impactful.`;
  }
  // ── Strengths ────────────────────────────────────────────────────────
  else if (q.includes('strength') || q.includes('best at') || q.includes('superpower')) {
    generatedText = `My greatest strength is my ability to combine **strong SQL and analytical fundamentals with curiosity and rapid learning under ambiguity**.\n\nWhen given a new or messy dataset, I'm comfortable diving in, understanding data schemas, diagnosing anomalies, and translating raw records into clear business insights. In hackathons like Tata Steel, I demonstrated the ability to pick up new problem domains quickly and deliver rigorous results under tight deadlines.`;
  }
  // ── General Human Fallback with Profile Context ────────────────────
  else {
    generatedText = isDataAnalyticsProfile
      ? `To answer that directly: from my background in data analytics and software engineering, I break problems down into three steps:\n\n1. **Clarify requirements and constraints**: understand the input data sources, schemas, and edge cases.\n2. **Develop and validate the solution**: whether writing clean SQL queries or Python scripts, I test against real data and objective metrics.\n3. **Communicate the outcome**: focus on clear, actionable takeaways rather than technical jargon.\n\nIn projects like Tata Steel and SOBUH, this approach helped ensure that our analysis directly supported reliable decisions. Happy to walk through any specific example or code if you'd like!`
      : `To approach that: I start by understanding the requirements and trade-offs, writing clean and testable logic, and validating against real metrics. I focus on end-to-end reliability and iterative improvement.`;
  }

  // Stream word-by-word with natural cadence
  let accumulated = '';
  const words = generatedText.split(' ');
  for (let i = 0; i < words.length; i++) {
    if (signal?.aborted) throw new Error('Generation aborted');
    const word = (i === 0 ? '' : ' ') + words[i];
    accumulated += word;
    onToken(word, accumulated);
    await new Promise((res) => setTimeout(res, 4));
  }

  return accumulated;
}



/**
 * Direct call to local Next.js Serverless Streaming Proxy (/api/interview)
 */
async function streamFromServerlessProxy(
  systemPrompt: string,
  question: string,
  keys: any,
  onToken: (token: string, accumulated: string) => void,
  signal?: AbortSignal
): Promise<string> {
  const res = await fetch('/api/interview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, systemPrompt, keys }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Serverless proxy failed with status ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith(':')) continue;
      if (trimmed === 'data: [DONE]') break;
      if (trimmed.startsWith('data: ')) {
        try {
          const json = JSON.parse(trimmed.slice(6));
          const delta = json.choices?.[0]?.delta?.content
            || json.candidates?.[0]?.content?.parts?.[0]?.text
            || '';
          if (delta) {
            accumulated += delta;
            onToken(delta, accumulated);
          }
        } catch {
          // ignore stream parse errors
        }
      }
    }
  }

  return accumulated;
}

/**
 * Master Stream Answer Function
 */
export async function streamUniversalAnswer(
  options: InterviewStreamOptions
): Promise<{ text: string; source: 'groq' | 'openai' | 'gemini' | 'openrouter' | 'serverless_proxy' | 'arceus_backend' | 'smart_fallback' }> {
  const keys = getStoredApiKeys();
  const systemPrompt = buildSystemPrompt(options);

  // 1. Direct Groq API (Cascades 70B -> 8B-instant to avoid rate limits)
  if (keys.groq) {
    for (const model of ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it']) {
      try {
        const text = await streamFromOpenAiCompatible(
          'https://api.groq.com/openai/v1/chat/completions',
          keys.groq,
          model,
          [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: options.question },
          ],
          (chunk, acc) => options.onToken(chunk, acc),
          options.signal
        );
        if (text.trim()) return { text, source: 'groq' };
      } catch (err: any) {
        console.warn(`Groq ${model} direct stream failed, trying next:`, err);
      }
    }
  }

  // 2. Direct OpenAI API
  if (keys.openai) {
    try {
      const text = await streamFromOpenAiCompatible(
        'https://api.openai.com/v1/chat/completions',
        keys.openai,
        'gpt-4o-mini',
        [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: options.question },
        ],
        (chunk, acc) => options.onToken(chunk, acc),
        options.signal
      );
      if (text.trim()) return { text, source: 'openai' };
    } catch (err: any) {
      console.warn('OpenAI direct stream failed, trying serverless proxy:', err);
    }
  }

  // 3. Direct Gemini API
  if (keys.gemini) {
    try {
      const text = await streamFromGemini(
        keys.gemini,
        'gemini-1.5-flash',
        systemPrompt,
        options.question,
        (chunk, acc) => options.onToken(chunk, acc),
        options.signal
      );
      if (text.trim()) return { text, source: 'gemini' };
    } catch (err: any) {
      console.warn('Gemini direct stream failed, trying serverless proxy:', err);
    }
  }

  // 4. Serverless Edge Proxy on Next.js (/api/interview)
  try {
    const text = await streamFromServerlessProxy(
      systemPrompt,
      options.question,
      keys,
      (chunk, acc) => options.onToken(chunk, acc),
      options.signal
    );
    if (text.trim()) {
      return { text, source: 'serverless_proxy' };
    }
  } catch (err: any) {
    console.warn('Serverless proxy stream failed:', err);
  }

  // 5. Try Arceus Backend Agent if available
  try {
    const backendUrl = '/api/v1/agents/chat';
    const body = {
      message: options.question,
      session_id: 'interview',
      llm_provider: 'autonomus',
      llm_model: 'autonomus-ai-v1',
      persist: false,
      interview_style: options.interviewStyle || 'short',
      target_role: options.targetRole || '',
      target_company: options.targetCompany || '',
      project_notes: options.projectNotes || '',
      interview_prompt: options.interviewPrompt || '',
    };

    const res = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options.signal,
    });

    if (res.ok && res.body && !res.redirected) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulated = '';
      let currentEvent = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim();
          } else if (trimmed.startsWith('data:')) {
            try {
              const payload = JSON.parse(trimmed.slice(5).trim());
              if (currentEvent === 'token' && payload.token) {
                accumulated += payload.token;
                options.onToken(payload.token, accumulated);
              }
            } catch {
              // ignore
            }
          }
        }
      }

      if (accumulated.trim()) {
        return { text: accumulated, source: 'arceus_backend' };
      }
    }
  } catch (err) {
    console.warn('Arceus backend unreachable, activating smart offline fallback generator:', err);
  }

  // 5. Always-Available Smart Fallback (Guaranteed to return intelligent response!)
  const text = await streamSmartFallback(options, (chunk, acc) => options.onToken(chunk, acc), options.signal);
  return { text, source: 'smart_fallback' };
}

export function generateClientInterviewPlan(
  role: string = 'Software Engineer',
  company: string = 'the target company',
  jobDescription: string = ''
): string {
  const targetRole = role.trim() || 'Software Engineer';
  const targetCompany = company.trim() || 'Target Company';

  return `# Comprehensive Interview Strategy for ${targetRole}

## Candidate Story Arc
- **Elevator Pitch**: Connect your background, core technical focus, and greatest engineering achievement in a 60-second narrative.
- **Top Technical Strength**: Lead with real-world system architecture, problem-solving speed, and reliable execution.
- **Strategic Growth Area**: Frame continuous learning around emerging distributed patterns or system optimization.

## Behavioral / HR
1. **Tell me about yourself.**
   - *Strategy*: 45-60 second spoken pitch: background, primary tech stack, impactful project, and why ${targetCompany} is the ideal next step.
2. **Why should we hire you?**
   - *Strategy*: Emphasize ownership, fast ramp-up time, clean code habits, and specific alignment with ${targetRole} responsibilities.
3. **Describe a challenge you solved.**
   - *Strategy*: STAR framework: Outline the situation, the technical blocker, your specific action, and the quantified outcome.
4. **How do you handle disagreement in code reviews?**
   - *Strategy*: Focus on objective data, benchmarking, team consensus, and prioritizing long-term maintainability over ego.

## Technical & Architecture
1. **How do you design a resilient API for high-traffic services?**
   - *Strategy*: Detail REST/GraphQL design, validation, idempotency, rate limiting, connection pooling, and multi-tier caching.
2. **Explain your approach to debugging production regressions.**
   - *Strategy*: Isolate logs, reproduce in staging, inspect telemetry/metrics, write regression test, and deploy canary fix.
3. **How do you optimize frontend rendering and load times?**
   - *Strategy*: Code-splitting, asset compression, memoization, Server-Side Rendering (SSR), and optimizing Critical Rendering Path.

## Questions To Ask The Interviewer
1. *What does success look like for this ${targetRole} role in the first 90 days?*
2. *What are the most interesting architectural challenges ${targetCompany}'s team is tackling this quarter?*
3. *How does the team balance shipping new features with reducing technical debt?*
`;
}

