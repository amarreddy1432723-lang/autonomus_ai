import React from 'react';

interface MarkdownRendererProps {
  content: string;
  onExplainImage?: (image: { url: string; alt: string }) => void;
}

export default function MarkdownRenderer({ content, onExplainImage }: MarkdownRendererProps) {
  if (!content) return null;

  // Split content into blocks: code blocks, tables, lists, and paragraphs.
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  const elements: React.ReactNode[] = [];
  let currentTableLines: string[] = [];
  let inTable = false;

  const flushTable = (index: number) => {
    if (currentTableLines.length === 0) return;
    
    const rows = currentTableLines.map(line => {
      const parts = line.split('|');
      if (parts[0].trim() === '') parts.shift();
      if (parts[parts.length - 1]?.trim() === '') parts.pop();
      return parts.map(p => p.trim());
    });

    const hasSeparator = rows[1] && rows[1].every(cell => /^:-*-*:?$/.test(cell) || /^-+$/.test(cell));
    const headerRow = rows[0] || [];
    const bodyRows = hasSeparator ? rows.slice(2) : rows.slice(1);

    elements.push(
      <div key={`table-${index}`} style={{ overflowX: 'auto', margin: '12px 0' }}>
        <table>
          <thead>
            <tr>
              {headerRow.map((cell, idx) => (
                <th key={`th-${idx}`}>{parseInline(cell, onExplainImage)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bodyRows.map((row, rowIdx) => (
              <tr key={`tr-${rowIdx}`}>
                {row.map((cell, cellIdx) => (
                  <td key={`td-${cellIdx}`}>{parseInline(cell, onExplainImage)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
    currentTableLines = [];
    inTable = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isTableLine = line.trim().startsWith('|') && line.trim().endsWith('|');

    if (isTableLine) {
      inTable = true;
      currentTableLines.push(line);
    } else {
      if (inTable) {
        flushTable(i);
      }

      // Check for bullet points
      if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
        const itemContent = line.trim().slice(2);
        elements.push(
          <ul key={`ul-${i}`} style={{ paddingLeft: '20px', margin: '4px 0', listStyleType: 'disc' }}>
            <li>{parseInline(itemContent, onExplainImage)}</li>
          </ul>
        );
      } else if (/^\d+\.\s/.test(line.trim())) {
        const match = line.trim().match(/^(\d+)\.\s(.*)/);
        if (match) {
          const num = match[1];
          const itemContent = match[2];
          elements.push(
            <ol key={`ol-${i}`} start={parseInt(num)} style={{ paddingLeft: '20px', margin: '4px 0' }}>
              <li>{parseInline(itemContent, onExplainImage)}</li>
            </ol>
          );
        }
      } else if (line.trim() === '') {
        elements.push(<div key={`spacer-${i}`} style={{ height: '8px' }} />);
      } else {
        elements.push(
          <p key={`p-${i}`} style={{ margin: '8px 0', lineHeight: '1.6' }}>
            {parseInline(line, onExplainImage)}
          </p>
        );
      }
    }
  }

  if (inTable) {
    flushTable(lines.length);
  }

  return <>{elements}</>;
}

function parseInline(
  text: string,
  onExplainImage?: (image: { url: string; alt: string }) => void
): React.ReactNode {
  const imageRegex = /!\[(.*?)\]\((.*?)\)/g;
  const linkRegex = /\[(.*?)\]\((.*?)\)/g;
  const boldRegex = /\*\*(.*?)\*\*/g;
  const codeRegex = /`(.*?)`/g;

  // Check for YouTube video link first
  const isYoutube = text.match(/(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/);
  if (isYoutube) {
    const videoId = isYoutube[1];
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', margin: '12px 0' }}>
        <span style={{ fontWeight: '600', color: 'var(--color-text-secondary)', fontSize: '0.8rem' }}>
          📹 Video Resource:
        </span>
        <div style={{ position: 'relative', paddingBottom: '56.25%', height: 0, overflow: 'hidden', borderRadius: '8px', boxShadow: 'var(--shadow-md)' }}>
          <iframe
            src={`https://www.youtube.com/embed/${videoId}`}
            title="YouTube video player"
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', border: 0 }}
          />
        </div>
      </div>
    );
  }

  // Check for direct video links
  const isDirectVideo = text.match(/(https?:\/\/.*?\.(?:mp4|webm|ogg))/i);
  if (isDirectVideo) {
    const videoUrl = isDirectVideo[1];
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', margin: '12px 0' }}>
        <span style={{ fontWeight: '600', color: 'var(--color-text-secondary)', fontSize: '0.8rem' }}>
          📹 Video Resource:
        </span>
        <video 
          src={videoUrl} 
          controls 
          style={{ width: '100%', borderRadius: '8px', boxShadow: 'var(--shadow-md)', maxHeight: '360px' }} 
        />
      </div>
    );
  }

  // Check for images
  const imgMatches = [...text.matchAll(imageRegex)];
  if (imgMatches.length > 0) {
    const alt = imgMatches[0][1];
    const url = imgMatches[0][2];
    
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '12px 0', alignItems: 'center' }}>
        {onExplainImage ? (
          <button
            type="button"
            onClick={() => onExplainImage({ url, alt })}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onExplainImage({ url, alt });
              }
            }}
            aria-label={`Explain image${alt ? `: ${alt}` : ''}`}
            style={{
              width: '100%',
              padding: 0,
              border: 'none',
              background: 'transparent',
              cursor: 'zoom-in',
              display: 'flex',
              justifyContent: 'center'
            }}
          >
            <img
              src={url}
              alt={alt}
              style={{ maxWidth: '100%', borderRadius: '8px', boxShadow: 'var(--shadow-md)', border: '1px solid var(--color-border)', objectFit: 'contain', maxHeight: '400px' }}
            />
          </button>
        ) : (
          <img
            src={url}
            alt={alt}
            style={{ maxWidth: '100%', borderRadius: '8px', boxShadow: 'var(--shadow-md)', border: '1px solid var(--color-border)', objectFit: 'contain', maxHeight: '400px' }}
          />
        )}
        {alt && (
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', fontStyle: 'italic', textAlign: 'center' }}>
            {alt}
          </span>
        )}
      </div>
    );
  }

  let parts: React.ReactNode[] = [text];

  // 1. Process bold text
  parts = parts.flatMap(part => {
    if (typeof part !== 'string') return part;
    const split = part.split(boldRegex);
    return split.map((sub, idx) => (idx % 2 === 1 ? <strong key={`b-${idx}`}>{sub}</strong> : sub));
  });

  // 2. Process inline code
  parts = parts.flatMap(part => {
    if (typeof part !== 'string') return part;
    const split = part.split(codeRegex);
    return split.map((sub, idx) => (idx % 2 === 1 ? <code key={`c-${idx}`} style={{ background: 'var(--color-bg-tertiary)', padding: '2px 4px', borderRadius: '4px', fontFamily: 'monospace', fontSize: '0.85em' }}>{sub}</code> : sub));
  });

  // 3. Process links
  parts = parts.flatMap(part => {
    if (typeof part !== 'string') return part;
    const matches = [...part.matchAll(linkRegex)];
    if (matches.length === 0) return part;

    const result: React.ReactNode[] = [];
    let lastIndex = 0;
    matches.forEach((match, idx) => {
      const matchIndex = match.index || 0;
      if (matchIndex > lastIndex) {
        result.push(part.substring(lastIndex, matchIndex));
      }
      const label = match[1];
      const url = match[2];
      result.push(
        <a 
          key={`link-${idx}`} 
          href={url} 
          target="_blank" 
          rel="noopener noreferrer" 
          style={{ color: 'var(--color-accent-primary)', textDecoration: 'underline' }}
        >
          {label}
        </a>
      );
      lastIndex = matchIndex + match[0].length;
    });

    if (lastIndex < part.length) {
      result.push(part.substring(lastIndex));
    }

    return result;
  });

  return <>{parts}</>;
}
