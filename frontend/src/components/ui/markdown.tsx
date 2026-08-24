import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  return (
    <div className={`leading-relaxed text-sm ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-1.5 last:mb-0 leading-relaxed">{children}</p>,
          strong: ({ children }) => <strong className="font-bold text-inherit">{children}</strong>,
          b: ({ children }) => <b className="font-bold text-inherit">{children}</b>,
          em: ({ children }) => <em className="italic text-inherit">{children}</em>,
          ul: ({ children }) => <ul className="my-1.5 list-disc pl-4 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1.5 list-decimal pl-4 space-y-0.5">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          code: ({ children }) => (
            <code className="rounded bg-black/10 dark:bg-white/10 px-1 py-0.5 font-mono text-[12px]">
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="underline hover:opacity-80"
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
