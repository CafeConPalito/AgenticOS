import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { ConnectionList } from '@/components/connections/ConnectionList'
import { ServerExplorer } from '@/components/connections/registry/ServerExplorer'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const VIEWS = { catalog: 'catalogo', explore: 'explorar' } as const
type View = keyof typeof VIEWS

/** «Conexiones»: the MCP servers the agents can use, and the public registries to find more.
 * The view is in the URL (`?vista=`), so it can be linked. */
export default function ConnectionsPage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const view =
    (Object.keys(VIEWS) as View[]).find((v) => VIEWS[v] === params.get('vista')) ?? 'catalog'
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col">
      <header className="px-6 pt-[22px]">
        <h1 className="text-[22px] leading-[1.3] font-medium tracking-[-0.01em]">
          {t('nav.connections')}
        </h1>
      </header>
      <Tabs
        value={view}
        onValueChange={(next) => {
          const updated = new URLSearchParams(params)
          if (next === 'catalog') updated.delete('vista')
          else updated.set('vista', VIEWS[next as View])
          setParams(updated, { replace: true })
        }}
        className="mt-3 gap-0"
      >
        <TabsList className="mx-6">
          {(Object.keys(VIEWS) as View[]).map((v) => (
            <TabsTrigger key={v} value={v}>
              {t(`connections.pageTabs.${v}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="catalog">
          <ConnectionList explore initialOpen={params.get('conexion')} />
        </TabsContent>
        <TabsContent value="explore">
          <ServerExplorer />
        </TabsContent>
      </Tabs>
    </div>
  )
}
