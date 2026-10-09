import { Route, Routes } from 'react-router-dom'
import Layout from '@/components/Layout'
import AdiantamentoFormPage from '@/pages/AdiantamentoFormPage'
import AlimentacaoFormPage from '@/pages/AlimentacaoFormPage'
import DetalhePage from '@/pages/DetalhePage'
import ListaPage from '@/pages/ListaPage'
import NotFoundPage from '@/pages/NotFoundPage'
import PerfilPage from '@/pages/PerfilPage'
import PrestacaoPage from '@/pages/PrestacaoPage'
import ViagemFormPage from '@/pages/ViagemFormPage'
import WelcomePage from '@/pages/WelcomePage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<WelcomePage />} />
      <Route element={<Layout />}>
        <Route
          path="/inicio"
          element={
            <ListaPage
              key="minhas"
              escopo="minhas"
              titulo="Meus reembolsos"
              descricao="Acompanhe aqui o andamento de cada pedido."
              vazio="Você ainda não pediu nenhum reembolso."
            />
          }
        />
        <Route
          path="/conferencia"
          element={
            <ListaPage
              key="conferencia"
              escopo="conferencia"
              titulo="Conferência"
              descricao="Pedidos, prestações de contas e devoluções aguardando a conferência do financeiro."
              vazio="Nada para conferir agora."
            />
          }
        />
        <Route
          path="/aprovacoes"
          element={
            <ListaPage
              key="aprovacao"
              escopo="aprovacao"
              titulo="Aprovações"
              descricao="Reembolsos já conferidos pelo financeiro, adiantamentos e diferenças aguardando a sua aprovação."
              vazio="Nenhum pedido aguardando a sua aprovação."
            />
          }
        />
        <Route
          path="/pagamentos"
          element={
            <ListaPage
              key="pagamento"
              escopo="pagamento"
              titulo="Pagamentos"
              descricao="Reembolsos, adiantamentos e diferenças aprovados, aguardando pagamento."
              vazio="Nenhum pagamento pendente."
            />
          }
        />
        <Route
          path="/todas"
          element={
            <ListaPage
              key="todas"
              escopo="todas"
              titulo="Todas as solicitações"
              descricao="Visão geral, em qualquer status."
              vazio="Nenhuma solicitação ainda."
            />
          }
        />
        <Route path="/nova" element={<AlimentacaoFormPage />} />
        <Route path="/nova/viagem" element={<ViagemFormPage />} />
        <Route path="/nova/adiantamento" element={<AdiantamentoFormPage />} />
        <Route path="/solicitacoes/:id" element={<DetalhePage />} />
        <Route path="/solicitacoes/:id/corrigir" element={<AlimentacaoFormPage />} />
        <Route path="/solicitacoes/:id/corrigir-viagem" element={<ViagemFormPage />} />
        <Route path="/solicitacoes/:id/corrigir-adiantamento" element={<AdiantamentoFormPage />} />
        <Route path="/solicitacoes/:id/prestar-contas" element={<PrestacaoPage />} />
        <Route path="/perfil" element={<PerfilPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
