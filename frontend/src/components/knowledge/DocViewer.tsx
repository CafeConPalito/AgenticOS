import { useTranslation } from 'react-i18next'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  imagePath,
  originalPath,
  useApiBase,
  useDocMarkdown,
  useOriginalText,
  type KnowledgeDoc,
} from '@/api/knowledge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

/** Rows of a CSV: comma or semicolon separated, quotes and doubled quotes understood. */
export function parseCsv(text: string): string[][] {
  const first = text.split(/\r?\n/, 1)[0] ?? ''
  const separator = (first.match(/;/g)?.length ?? 0) > (first.match(/,/g)?.length ?? 0) ? ';' : ','
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        cell += '"'
        i++
      } else if (char === '"') quoted = false
      else cell += char
    } else if (char === '"') quoted = true
    else if (char === separator) {
      row.push(cell)
      cell = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i++
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else cell += char
  }
  if (cell !== '' || row.length > 0) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

/** The Markdown of a document, with its pictures (`kimg:N`) shown from the backend. */
export function MarkdownView({ doc }: { doc: KnowledgeDoc }) {
  const { t } = useTranslation()
  const base = useApiBase()
  const markdown = useDocMarkdown(doc.id, doc.has_markdown)
  if (!doc.has_markdown)
    return <p className="text-muted-foreground">{t('knowledge.viewer.noMarkdown')}</p>
  if (markdown.isPending || base === null) return <Skeleton aria-busy className="h-40" />
  if (markdown.isError)
    return <p className="text-status-failed">{t('knowledge.viewer.loadFailed')}</p>
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-muted-foreground">
        {t('knowledge.viewer.tokens', { count: markdown.data.tokens })}
      </p>
      <div className="prose-sm max-w-none text-[13.5px] leading-relaxed [&_img]:max-h-96 [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-2 [&_table]:border-collapse [&_td]:border [&_td]:px-2 [&_th]:border [&_th]:px-2">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          urlTransform={(url) => {
            const picture = /^kimg:(\d+)$/.exec(url)
            return picture
              ? `${base}${imagePath(doc.id, Number(picture[1]))}`
              : defaultUrlTransform(url)
          }}
        >
          {markdown.data.markdown}
        </ReactMarkdown>
      </div>
    </div>
  )
}

function TextView({ doc, as }: { doc: KnowledgeDoc; as: 'text' | 'code' | 'csv' | 'markdown' }) {
  const { t } = useTranslation()
  const text = useOriginalText(doc.id, true)
  if (text.isPending) return <Skeleton aria-busy className="h-40" />
  if (text.isError) return <p className="text-status-failed">{t('knowledge.viewer.loadFailed')}</p>
  if (as === 'csv') {
    const rows = parseCsv(text.data).slice(0, 500)
    return (
      <div className="overflow-auto rounded border">
        <table className="w-full text-[12.5px]">
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={i === 0 ? 'bg-muted font-medium' : 'border-t'}>
                {row.map((cell, j) => (
                  <td key={j} className="px-2 py-1 align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return (
    <pre
      className={
        as === 'code'
          ? 'overflow-auto rounded border bg-muted p-3 font-mono text-[12.5px]'
          : 'overflow-auto rounded border p-3 text-[13px] whitespace-pre-wrap'
      }
    >
      {text.data}
    </pre>
  )
}

function OriginalView({ doc }: { doc: KnowledgeDoc }) {
  const { t } = useTranslation()
  const base = useApiBase()
  if (doc.presence === 'missing')
    return <p className="text-muted-foreground">{t('knowledge.viewer.originalMissing')}</p>
  if (doc.viewer === 'pdf') {
    if (base === null) return <Skeleton aria-busy className="h-96" />
    return (
      <iframe
        title={t('knowledge.viewer.pdfTitle', { title: doc.title })}
        src={`${base}${originalPath(doc.id)}`}
        className="h-[70vh] w-full rounded border"
      />
    )
  }
  if (doc.viewer === 'image') {
    if (base === null) return <Skeleton aria-busy className="h-96" />
    return (
      <img
        alt={doc.title}
        src={`${base}${originalPath(doc.id)}`}
        className="max-h-[70vh] max-w-full rounded border object-contain"
      />
    )
  }
  if (
    doc.viewer === 'markdown' ||
    doc.viewer === 'text' ||
    doc.viewer === 'code' ||
    doc.viewer === 'csv'
  )
    return <TextView doc={doc} as={doc.viewer} />
  return <p className="text-muted-foreground">{t('knowledge.viewer.noPreview')}</p>
}

const CAN_PREVIEW = ['pdf', 'image', 'markdown', 'text', 'code', 'csv']

/** «Original» (inside the app when its format allows) and «Markdown» (what the agents read). */
export function DocViewer({
  doc,
  initial = 'markdown',
}: {
  doc: KnowledgeDoc
  initial?: 'original' | 'markdown'
}) {
  const { t } = useTranslation()
  const original = CAN_PREVIEW.includes(doc.viewer)
  const start = original && (initial === 'original' || !doc.has_markdown) ? 'original' : 'markdown'
  return (
    <Tabs defaultValue={start}>
      <TabsList>
        {original && <TabsTrigger value="original">{t('knowledge.viewer.original')}</TabsTrigger>}
        <TabsTrigger value="markdown">{t('knowledge.viewer.markdown')}</TabsTrigger>
      </TabsList>
      {original && (
        <TabsContent value="original">
          <OriginalView doc={doc} />
        </TabsContent>
      )}
      <TabsContent value="markdown">
        <MarkdownView doc={doc} />
      </TabsContent>
    </Tabs>
  )
}
