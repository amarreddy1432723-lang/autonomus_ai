import { notFound } from 'next/navigation';

const scenes = [
  'Desktop shell signed out',
  'Desktop shell signed in',
  'API offline local mode',
  'Workspace empty',
  'Open folder file tree',
  'Editor chat terminal',
  'Agent receipt auto-applied',
  'Risky change review required',
  'Jobs drawer',
  'Preview verification',
  'Git PR flow',
  'Settings code',
  'Settings AI models',
  'Settings privacy vault',
  'Download page',
];

export default function ArceusCodeUiPreviewPage() {
  if (process.env.NODE_ENV === 'production' && process.env.NEXT_PUBLIC_ENABLE_UI_PREVIEWS !== 'true') {
    notFound();
  }

  return (
    <main style={{ minHeight: '100vh', background: '#08090e', color: '#f5f7fb', padding: 32, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <section style={{ maxWidth: 1120, margin: '0 auto', display: 'grid', gap: 20 }}>
        <div>
          <p style={{ color: '#9b8cff', fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase', fontSize: 12 }}>Arceus Code UI Preview</p>
          <h1 style={{ fontSize: 38, margin: '8px 0' }}>Desktop proof-first workspace storyboard</h1>
          <p style={{ color: '#9ca3af', maxWidth: 760 }}>
            This development-only page documents the intended desktop shell, offline recovery, and operational panel states.
            The generated PNG pack lives in <code>docs/ui-previews</code>.
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          {scenes.map((scene, index) => (
            <article key={scene} style={{ border: '1px solid #202634', background: '#11141c', borderRadius: 10, padding: 16 }}>
              <strong style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ display: 'grid', placeItems: 'center', width: 24, height: 24, borderRadius: 999, background: '#7c6cf0', color: 'white', fontSize: 12 }}>{index + 1}</span>
                {scene}
              </strong>
              <p style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.5 }}>
                See <code>docs/ui-previews/{String(index + 1).padStart(2, '0')}-*.png</code> for numbered button callouts and behavior notes.
              </p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
