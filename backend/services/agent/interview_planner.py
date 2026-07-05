import re
from collections.abc import Iterable


def _clean_lines(text: str, limit: int = 16) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip(" -|•") for line in (text or "").splitlines()]
    selected: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if len(line) < 4 or len(line) > 180:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(line)
        if len(selected) >= limit:
            break
    return selected


def _keywords(text: str, fallback: list[str]) -> list[str]:
    known = [
        "react", "next.js", "typescript", "javascript", "python", "fastapi", "node",
        "sql", "postgres", "mongodb", "aws", "docker", "rest api", "html", "css",
        "tailwind", "redux", "machine learning", "data analysis", "excel", "java",
    ]
    lowered = (text or "").lower()
    found = []
    for item in known:
        if item in lowered:
            found.append(item.title() if item != "rest api" else "REST API")
    return found[:8] or fallback


def build_interview_plan(
    resume_text: str,
    target_role: str = "",
    target_company: str = "",
    job_description: str = "",
) -> str:
    role = target_role.strip() or "the target role"
    company = target_company.strip() or "the company"
    resume_lines = _clean_lines(resume_text)
    evidence = "\n".join(f"- {line}" for line in resume_lines[:8]) or "- Resume details were uploaded and should be used as evidence."
    skills = _keywords(" ".join([resume_text, job_description, target_role]), ["core project work", "communication", "problem solving"])

    technical_questions = [
        f"Explain {skills[0]} in a project context.",
        "How would you design a REST API for a real product feature?",
        "How do you debug a performance issue in a frontend or backend service?",
        "How would you handle errors and edge cases in production code?",
        f"What tradeoff did you make in a project related to {skills[min(1, len(skills) - 1)]}?",
    ]

    return f"""# Interview Plan for {role}

## Candidate Story Arc
- Elevator pitch: connect education, strongest skills, and one practical project.
- Strength: choose one technical strength and back it with a project example.
- Weakness: choose a safe growth area and show how you are improving.
- Evidence to reuse:
{evidence}

## Behavioral / HR
1. Tell me about yourself.
   Answer: Give a 45-60 second first-person summary: background, strongest skill, best project, and why this role fits.
2. Why should we hire you?
   Answer: Mention role fit, learning speed, ownership, and one resume-backed example.
3. Tell me about a challenge you faced.
   Answer: Use STAR: situation, task, action, result, and what you learned.
4. What are your strengths and weaknesses?
   Answer: Strength with evidence; weakness with a concrete improvement habit.
5. Describe a time you worked in a team.
   Answer: Mention collaboration, your responsibility, conflict handling, and outcome.

## Technical
1. {technical_questions[0]}
   Answer: Define it simply, explain how it works, then connect to a real project only if supported by the resume.
2. {technical_questions[1]}
   Answer: Mention resources, endpoints, validation, status codes, authentication, database, and edge cases.
3. {technical_questions[2]}
   Answer: Explain measurement first, then common fixes like caching, batching, indexing, code splitting, or query optimization.
4. {technical_questions[3]}
   Answer: Cover validation, null states, retries, logging, user-friendly errors, and tests.
5. {technical_questions[4]}
   Answer: Describe the decision, alternatives, why you chose it, and what result it produced.

## Role-Specific Scenarios
1. You receive an unclear requirement. What do you do?
   Answer: Clarify goal, users, constraints, acceptance criteria, then prototype or break into tasks.
2. A feature works locally but fails in production. How do you approach it?
   Answer: Check logs, environment variables, network/API differences, build output, and rollback plan.
3. You have two deadlines at once. How do you prioritize?
   Answer: Align by business impact, risk, dependencies, and communicate tradeoffs early.

## Company-Specific
1. Why do you want to work at {company}?
   Answer: Connect the company/product area to your skills, learning goals, and role interest.
2. What value can you bring to {company} as {role}?
   Answer: Mention practical execution, fast learning, project evidence, and communication.

## Questions To Ask The Interviewer
1. What would success look like in the first 90 days for this role?
2. What kind of projects would I work on first?
3. How does the team review code, share knowledge, and support junior members?

## Live Answer Rules
- For technical/coding questions: direct answer first, short explanation, real example, resume connection only if true.
- For HR questions: concise first-person answer with one resume-backed proof point.
- Never invent metrics, companies, tools, or project details.
"""


def stream_plan_text(plan: str, chunk_size: int = 80) -> Iterable[str]:
    for index in range(0, len(plan), chunk_size):
        yield plan[index:index + chunk_size]
