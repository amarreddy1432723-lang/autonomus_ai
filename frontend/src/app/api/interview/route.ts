import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'edge';

interface RequestBody {
  question: string;
  systemPrompt: string;
  keys?: {
    groq?: string;
    openai?: string;
    gemini?: string;
    openrouter?: string;
  };
}

export async function POST(req: NextRequest) {
  try {
    const body: RequestBody = await req.json();
    const { question, systemPrompt, keys = {} } = body;

    const groqKey = keys.groq || process.env.GROQ_API_KEY;
    const geminiKey = keys.gemini || process.env.GEMINI_API_KEY;
    const openaiKey = keys.openai || process.env.OPENAI_API_KEY;

    // 1. Try Groq if key available (Cascading 70B -> 8B-instant to avoid rate limits)
    if (groqKey) {
      for (const groqModel of ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'gemma2-9b-it']) {
        try {
          const groqRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${groqKey}`,
            },
            body: JSON.stringify({
              model: groqModel,
              messages: [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: question },
              ],
              stream: true,
              temperature: 0.65,
            }),
          });

          if (groqRes.ok && groqRes.body) {
            return new Response(groqRes.body, {
              headers: {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                Connection: 'keep-alive',
              },
            });
          }
        } catch (err) {
          console.warn(`Server Groq ${groqModel} call failed:`, err);
        }
      }
    }

    // 2. Try Gemini if key available
    if (geminiKey) {
      try {
        const geminiRes = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:streamGenerateContent?key=${geminiKey}&alt=sse`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              contents: [
                {
                  role: 'user',
                  parts: [{ text: `${systemPrompt}\n\nQuestion: "${question}"\n\nAnswer:` }],
                },
              ],
            }),
          }
        );

        if (geminiRes.ok && geminiRes.body) {
          return new Response(geminiRes.body, {
            headers: {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
              Connection: 'keep-alive',
            },
          });
        }
      } catch (err) {
        console.warn('Server Gemini call failed:', err);
      }
    }

    // 3. Try OpenAI if key available
    if (openaiKey) {
      try {
        const openaiRes = await fetch('https://api.openai.com/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${openaiKey}`,
          },
          body: JSON.stringify({
            model: 'gpt-4o-mini',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: question },
            ],
            stream: true,
            temperature: 0.65,
          }),
        });

        if (openaiRes.ok && openaiRes.body) {
          return new Response(openaiRes.body, {
            headers: {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
              Connection: 'keep-alive',
            },
          });
        }
      } catch (err) {
        console.warn('Server OpenAI call failed:', err);
      }
    }

    return NextResponse.json({ ok: false, error: 'No live provider succeeded' }, { status: 502 });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message || 'Internal Server Error' }, { status: 500 });
  }
}

