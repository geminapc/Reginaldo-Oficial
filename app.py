import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import text
import urllib.parse

st.set_page_config(page_title="Frios & Geladão do Reginaldo", page_icon="🏪", layout="wide")

# --- CONEXÃO COM O POSTGRESQL (SUPABASE) ---
try:
    conn = st.connection("postgresql", type="sql")
    
    # 🛡️ GARANTIA: Garante que a tabela de clientes existe no banco oficial
    with conn.session as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                whatsapp VARCHAR(20) NOT NULL,
                endereco TEXT,
                bairro VARCHAR(100),
                observacoes TEXT,
                data_cadastro TIMESTAMP DEFAULT NOW()
            );
        """))
        session.commit()
except Exception as e:
    st.error(f"Erro ao inicializar conexão com o banco: {e}")

# Inicializa o carrinho e controle de mensagens na sessão se não existirem
if "carrinho" not in st.session_state:
    st.session_state.carrinho = []
if "ultima_venda" not in st.session_state:
    st.session_state.ultima_venda = None

# --- DESIGN PERSONALIZADO (CSS) ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    .total-card { background-color: #e8f5e9; padding: 20px; border-radius: 10px; border-left: 6px solid #2e7d32; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÃO AUXILIAR DE AUDITORIA (LOGS) ---
def registrar_movimentacao(session, produto, tipo, quantidade, anterior, novo, obs=""):
    try:
        session.execute(
            text("""
                INSERT INTO movimentacoes_estoque (produto, tipo_movimentacao, quantidade, estoque_anterior, estoque_novo, observacao)
                VALUES (:produto, :tipo, :qtd, :ant, :novo, :obs);
            """),
            {"produto": produto, "tipo": tipo, "qtd": quantidade, "ant": anterior, "novo": novo, "obs": obs}
        )
    except Exception as e:
        st.warning(f"Não foi possível salvar o histórico de movimentação: {e}")

# --- MENU LATERAL INTERATIVO ---
with st.sidebar:
    st.markdown("## 🏪 **Menu Principal**")
    tela = st.radio("Ir para:", [
        "💰 Frente de Caixa (Balcão)", 
        "👥 Cadastro de Clientes",
        "📦 Controle de Estoque", 
        "📋 Extrato do Estoque",
        "📊 Painel Financeiro"
    ])
    st.markdown("---")
    st.caption("Conectado ao Supabase PostgreSQL")

# -----------------------------------------------------------------------------------------
# TELA 1: FRENTE DE CAIXA
# -----------------------------------------------------------------------------------------
if tela == "💰 Frente de Caixa (Balcão)":
    # 🏢 NOME DA LOJA ADICIONADO NA TELA PRINCIPAL
    st.title("🛒 Frente de Caixa")
    st.subheader("🏪 Frios & Geladão do Reginaldo")
    st.markdown("---")
    
    try:
        df_est = conn.query("SELECT * FROM estoque ORDER BY produto;", ttl="0s")
        df_cli_venda = conn.query("SELECT id, nome, whatsapp FROM clientes ORDER BY nome;", ttl="0s")
    except Exception as e:
        st.error(f"Não foi possível ler o banco de dados: {e}")
        df_est = pd.DataFrame()
        df_cli_venda = pd.DataFrame()
        
    if df_est.empty:
        st.warning("Estoque zerado! Cadastre produtos na aba de Estoque.")
    else:
        col_venda, col_carrinho = st.columns([1.2, 1])
        
        with col_venda:
            st.markdown("### 1. Adicionar Produto")
            produtos_disponiveis = df_est[df_est['quantidade'] > 0]['produto'].tolist()
            
            if not produtos_disponiveis:
                st.error("🚨 Todos os produtos estão esgotados!")
            else:
                prod_selecionado = st.selectbox(
                    "Selecione o Produto",
                    options=produtos_disponiveis,
                    index=None,
                    placeholder="🔍 Digite o nome do produto para buscar..."
                )
                
                if prod_selecionado:
                    detalhes = df_est[df_est['produto'] == prod_selecionado].iloc[0]
                    unidades_pack = int(detalhes['unidades_por_pacote'])
                    qtd_maxima = int(detalhes['quantidade'] // unidades_pack) if detalhes['tipo_venda'] == "Fardo/Fechado" else int(detalhes['quantidade'])
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Preço", f"R$ {float(detalhes['preco_venda']):.2f}")
                    c2.metric("Estoque Atual", f"{qtd_maxima} fardos" if detalhes['tipo_venda'] == "Fardo/Fechado" else f"{qtd_maxima} un")
                    c3.metric("Tipo de Venda", str(detalhes['tipo_venda']))
                    
                    st.markdown("---")
                    qtd_venda = st.number_input("Quantidade desejada", min_value=1, max_value=max(1, qtd_maxima), value=1, step=1)
                    
                    if st.button("➕ Adicionar ao Pedido"):
                        ja_no_carrinho = False
                        for item in st.session_state.carrinho:
                            if item['produto'] == prod_selecionado:
                                if item['quantidade'] + qtd_venda <= qtd_maxima:
                                    item['quantidade'] += qtd_venda
                                    item['subtotal'] = item['quantidade'] * float(detalhes['preco_venda'])
                                    item['unidades_totais'] = item['quantidade'] * unidades_pack
                                    if detalhes['tipo_venda'] == "Fardo/Fechado":
                                        item['custo_total'] = float(detalhes['custo']) * item['quantidade']
                                    else:
                                        item['custo_total'] = (float(detalhes['custo']) / unidades_pack) * item['unidades_totais']
                                    ja_no_carrinho = True
                                else:
                                    st.error("Quantidade total excede o estoque disponível!")
                                    ja_no_carrinho = True
                        
                        if not ja_no_carrinho:
                            if detalhes['tipo_venda'] == "Fardo/Fechado":
                                custo_calculado = float(detalhes['custo']) * qtd_venda
                            else:
                                custo_calculado = (float(detalhes['custo']) / unidades_pack) * (qtd_venda * unidades_pack)

                            st.session_state.carrinho.append({
                                "produto": prod_selecionado,
                                "quantidade": qtd_venda,
                                "preco_venda": float(detalhes['preco_venda']),
                                "custo_total": custo_calculado,
                                "unidades_totais": qtd_venda * unidades_pack,
                                "subtotal": qtd_venda * float(detalhes['preco_venda'])
                            })
                        st.rerun()

        with col_carrinho:
            st.markdown("### 📋 Carrinho de Compras")
            if not st.session_state.carrinho:
                st.info("O carrinho está vazio.")
                
                # 📲 NOME DA LOJA ADICIONADO NA MENSAGEM DO WHATSAPP
                if st.session_state.ultima_venda:
                    st.success("✨ Venda registrada com sucesso!")
                    uv = st.session_state.ultima_venda
                    msg = f"Olá! Seu pedido no *Frios & Geladão do Reginaldo* ficou pronto.\nTotal: R$ {uv['total']:.2f}\nForma de Pagamento: {uv['pagamento']}\nObrigado pela preferência!"
                    msg_encodada = urllib.parse.quote(msg)
                    link_wa = f"https://wa.me/{uv['telefone']}?text={msg_encodada}"
                    
                    st.link_button("💬 Enviar Comprovante no WhatsApp", link_wa, type="primary")
                    if st.button("Limpar Alerta"):
                        st.session_state.ultima_venda = None
                        st.rerun()
            else:
                df_cart = pd.DataFrame(st.session_state.carrinho)
                st.dataframe(df_cart[['produto', 'quantidade', 'subtotal']].rename(columns={
                    'produto': 'Item', 'quantidade': 'Qtd', 'subtotal': 'Subtotal (R$)'
                }), use_container_width=True)
                
                total_geral = df_cart['subtotal'].sum()
                
                st.markdown(f"""
                    <div class="total-card"><p style="margin:0;">TOTAL DO PEDIDO</p><h2 style="margin:0;color:#2e7d32;">R$ {total_geral:.2f}</h2></div>
                    """, unsafe_allow_html=True)
                
                cliente_id = None
                telefones_dict = {}
                if not df_cli_venda.empty:
                    opcoes_cliente = ["Consumidor Não Identificado"]
                    for _, r_cli in df_cli_venda.iterrows():
                        nome_exibir = f"{r_cli['nome']} ({r_cli['whatsapp']})"
                        opcoes_cliente.append(nome_exibir)
                        telefones_dict[nome_exibir] = ''.join(filter(str.isdigit, str(r_cli['whatsapp'])))
                    
                    cli_selecionado = st.selectbox("Vincular Cliente (Opcional)", opcoes_cliente)
                    num_telefone = telefones_dict.get(cli_selecionado, "")
                else:
                    st.caption("Nenhum cliente cadastrado para vincular.")
                    num_telefone = ""
                
                forma_pagamento = st.selectbox("Forma de Pagamento", ["PIX", "Dinheiro", "Cartao"])
                
                if forma_pagamento == "Dinheiro":
                    pago = st.number_input("Valor Entregue", min_value=float(total_geral), value=float(total_geral))
                    if pago > total_geral:
                        st.success(f"💵 Troco: **R$ {pago - total_geral:.2f}**")
                
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("❌ Limpar Carrinho"):
                    st.session_state.carrinho = []
                    st.rerun()
                    
                if c_btn2.button("✅ Confirmar Venda"):
                    try:
                        with conn.session as session:
                            for item in st.session_state.carrinho:
                                res = session.execute(text("SELECT quantidade FROM estoque WHERE produto = :p;"), {"p": item['produto']}).fetchone()
                                estoque_atual = res[0] if res else 0
                                novo_estoque = estoque_atual - item['unidades_totais']

                                session.execute(
                                    text("UPDATE estoque SET quantidade = :novo WHERE produto = :prod;"),
                                    {"novo": novo_estoque, "prod": item['produto']}
                                )
                                lucro_item = item['subtotal'] - item['custo_total']
                                session.execute(
                                    text("INSERT INTO vendas (data_hora, produto, quantidade, valor_total, lucro, pagamento) VALUES (:dt, :prod, :qtd, :val, :luc, :pag);"),
                                    {"dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "prod": item['produto'], "qtd": item['quantidade'], "val": item['subtotal'], "luc": lucro_item, "pag": forma_pagamento}
                                )
                                registrar_movimentacao(session, item['produto'], "VENDA", item['unidades_totais'], estoque_atual, novo_estoque, f"Venda no balcão via {forma_pagamento}")
                            
                            session.commit()
                        
                        if num_telefone:
                            st.session_state.ultima_venda = {"total": total_geral, "telefone": num_telefone, "pagamento": forma_pagamento}
                        else:
                            st.session_state.ultima_venda = None
                            
                        st.session_state.carrinho = []
                        st.balloons()
                        st.rerun()
                    except Exception as err:
                        st.error(f"Falha ao salvar no banco: {err}")

# O restante do código (Cadastro de Clientes, Estoque, Extrato, Financeiro) continua exatamente o mesmo...
elif tela == "👥 Cadastro de Clientes":
    st.title("👥 Gestão e Cadastro de Clientes")
    try:
        df_clientes = conn.query("SELECT * FROM clientes ORDER BY nome;", ttl="0s")
    except Exception as e:
        st.error(f"Erro ao carregar clientes: {e}")
        df_clientes = pd.DataFrame()
    busca_cli = st.text_input("🔍 Buscar Cliente", placeholder="Digite o nome ou bairro do cliente...")
    if busca_cli and not df_clientes.empty:
        df_clientes = df_clientes[df_clientes["nome"].str.contains(busca_cli, case=False, na=False) | df_clientes["bairro"].str.contains(busca_cli, case=False, na=False)]
    st.subheader("📋 Clientes Registrados")
    if not df_clientes.empty:
        st.dataframe(df_clientes[['nome', 'whatsapp', 'endereco', 'bairro', 'observacoes']].rename(columns={'nome': 'Nome do Cliente', 'whatsapp': 'WhatsApp/Celular', 'endereco': 'Endereço', 'bairro': 'Bairro', 'observacoes': 'Notas/Obs'}), use_container_width=True)
    else:
        st.info("Nenhum cliente cadastrado ou encontrado.")
    st.divider()
    st.subheader("➕ Registrar Novo Cliente")
    with st.form("cadastro_cliente"):
        c_nome = st.text_input("Nome Completo")
        c_whats = st.text_input("WhatsApp (Ex: 85999999999 - Apenas números com DDD)")
        c_end = st.text_input("Endereço (Rua, Número, Apto)")
        c_bairro = st.text_input("Bairro")
        c_obs = st.text_area("Observações de Entrega / Notas")
        salvar_cliente = st.form_submit_button("💾 Salvar Cliente")
        if salvar_cliente and c_nome and c_whats:
            try:
                with conn.session as session:
                    session.execute(text("INSERT INTO clientes (nome, whatsapp, endereco, bairro, observacoes) VALUES (:nome, :whats, :end, :bairro, :obs);"), {"nome": c_nome, "whats": c_whats, "end": c_end, "bairro": c_bairro, "obs": c_obs})
                    session.commit()
                st.success(f"Cliente '{c_nome}' cadastrado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao cadastrar cliente: {e}")
        elif salvar_cliente:
            st.warning("Por favor, preencha pelo menos o Nome e o WhatsApp do cliente.")

elif tela == "📦 Controle de Estoque":
    st.title("📦 Controle de Estoque Profissional")
    try:
        df_estoque = conn.query("SELECT * FROM estoque ORDER BY produto;", ttl="0s")
    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        df_estoque = pd.DataFrame()
    busca = st.text_input("🔍 Buscar produto", placeholder="Digite o nome do produto...")
    if busca and not df_estoque.empty:
        df_estoque = df_estoque[df_estoque["produto"].str.contains(busca, case=False, na=False)]
    if not df_estoque.empty:
        produtos_baixos = df_estoque[df_estoque["quantidade"] <= 10]
        if not produtos_baixos.empty:
            st.warning(f"⚠️ Atenção: {len(produtos_baixos)} produto(s) com estoque baixo (10 unidades ou menos).")
    st.subheader("📋 Estoque Atual")
    if not df_estoque.empty:
        df_exibicao = df_estoque[['produto', 'preco_venda', 'quantidade', 'tipo_venda']].rename(columns={'produto': 'Nome do Produto', 'preco_venda': 'Preço de Venda (R$)', 'quantidade': 'Qtd em Estoque', 'tipo_venda': 'Modo de Venda'})
        st.dataframe(df_exibicao, use_container_width=True)
    else:
        st.info("Nenhum produto cadastrado.")
    st.divider()
    st.subheader("➕ Cadastrar ou Atualizar Produto")
    with st.form("cadastro_produto"):
        nome = st.text_input("Produto")
        tipo = st.selectbox("Tipo de Venda", ["Unidade Avulsa", "Fardo/Fechado"])
        pack = st.number_input("Unidades por pacote/fardo", min_value=1, value=1)
        custo = st.number_input("Preço de Custo Total (R$)", min_value=0.0, value=0.0)
        margem = st.number_input("Margem (%)", min_value=0.0, value=50.0)
        quantidade = st.number_input("Quantidade de fardos/unidades compradas", min_value=0, value=0)
        salvar = st.form_submit_button("💾 Salvar Produto")
        if salvar and nome:
            preco_venda = custo * (1 + margem / 100)
            unidades_totais = int(quantidade * pack)
            try:
                with conn.session as session:
                    res = session.execute(text("SELECT quantidade FROM estoque WHERE produto = :p;"), {"p": nome}).fetchone()
                    est_anterior = res[0] if res else 0
                    est_novo = est_anterior + unidades_totais
                    session.execute(text("""
                        INSERT INTO estoque (produto, custo, preco_venda, quantidade, unidades_por_pacote, tipo_venda)
                        VALUES (:produto, :custo, :preco, :qtd, :pack, :tipo)
                        ON CONFLICT (produto)
                        DO UPDATE SET custo = :custo, preco_venda = :preco, quantidade = estoque.quantidade + :qtd, unidades_por_pacote = :pack, tipo_venda = :tipo;
                        """), {"produto": nome, "custo": custo, "preco": preco_venda, "qtd": unidades_totais, "pack": pack, "tipo": tipo})
                    registrar_movimentacao(session, nome, "ENTRADA", unidades_totais, est_anterior, est_novo, "Entrada de mercadoria/Cadastro")
                    session.commit()
                st.success(f"Produto '{nome}' salvo!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
    st.divider()
    if not df_estoque.empty:
        st.subheader("✏️ Ajustar Estoque Manualmente")
        produto_ajuste = st.selectbox("Selecione o Produto para ajustar", df_estoque["produto"].tolist(), key="ajuste_produto")
        qtd_atual = int(df_estoque[df_estoque["produto"] == produto_ajuste]["quantidade"].values[0])
        nova_qtd = st.number_input("Nova Quantidade Exata em Estoque", min_value=0, value=qtd_atual)
        if st.button("Salvar Ajuste"):
            try:
                with conn.session as session:
                    session.execute(text("UPDATE estoque SET quantidade = :qtd WHERE produto = :produto"), {"qtd": nova_qtd, "produto": produto_ajuste})
                    registrar_movimentacao(session, produto_ajuste, "AJUSTE", (nova_qtd - qtd_atual), qtd_atual, nova_qtd, "Ajuste manual de inventário")
                    session.commit()
                st.success("Estoque atualizado!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
    st.divider()
    if not df_estoque.empty:
        st.subheader("🗑️ Excluir Produto")
        produto_excluir = st.selectbox("Produto para excluir", df_estoque["produto"].tolist(), key="excluir_produto")
        qtd_antes_del = int(df_estoque[df_estoque["produto"] == produto_excluir]["quantidade"].values[0])
        if st.button("Excluir Produto Definitivamente"):
            try:
                with conn.session as session:
                    session.execute(text("DELETE FROM estoque WHERE produto = :produto"), {"produto": produto_excluir})
                    registrar_movimentacao(session, produto_excluir, "EXCLUIR", qtd_antes_del, qtd_antes_del, 0, "Produto deletado do sistema")
                    session.commit()
                st.success("Produto excluído!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

elif tela == "📋 Extrato do Estoque":
    st.title("📋 Extrato e Auditoria de Estoque")
    st.caption("Acompanhe o histórico de todas as entradas, vendas e ajustes feitos no sistema.")
    try:
        df_mov = conn.query("SELECT data_hora, produto, tipo_movimentacao, quantidade, estoque_anterior, estoque_novo, observacao FROM movimentacoes_estoque ORDER BY id DESC;", ttl="0s")
    except:
        df_mov = pd.DataFrame()
    if df_mov.empty:
        st.info("Nenhuma movimentação registrada no histórico ainda.")
    else:
        df_mov_friendly = df_mov.rename(columns={'data_hora': 'Data/Hora', 'produto': 'Produto', 'tipo_movimentacao': 'Operação', 'quantidade': 'Qtd Movimentada', 'estoque_anterior': 'Estoque Antigo', 'estoque_novo': 'Estoque Novo', 'observacao': 'Detalhes'})
        st.dataframe(df_mov_friendly, use_container_width=True)

else:
    st.title("📊 Painel Financeiro & Dashboard Gerencial")
    try:
        df_est_fin = conn.query("SELECT custo, quantidade, unidades_por_pacote, tipo_venda FROM estoque;", ttl="0s")
    except:
        df_est_fin = pd.DataFrame()
    valor_estoque_custo = 0.0
    total_produtos_tipos = 0
    if not df_est_fin.empty:
        total_produtos_tipos = len(df_est_fin)
        for _, row in df_est_fin.iterrows():
            u_pack = int(row['unidades_por_pacote'])
            if row['tipo_venda'] == "Fardo/Fechado":
                custo_unitario = float(row['custo']) / u_pack
            else:
                custo_unitario = float(row['custo'])
            valor_estoque_custo += (custo_unitario * int(row['quantidade']))
    try:
        df_vendas = conn.query("SELECT * FROM vendas ORDER BY id DESC;", ttl="0s")
    except:
        df_vendas = pd.DataFrame()
    if df_vendas.empty:
        st.info("Nenhuma venda realizada ainda para gerar estatísticas.")
        if valor_estoque_custo > 0:
            st.metric("📦 Capital Empatado em Estoque (Preço de Custo)", f"R$ {valor_estoque_custo:.2f}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Faturamento Bruto", f"R$ {df_vendas['valor_total'].sum():.2f}")
        c2.metric("📈 Lucro Líquido Real", f"R$ {df_vendas['lucro'].sum():.2f}")
        c3.metric("📦 Valor em Estoque (Custo)", f"R$ {valor_estoque_custo:.2f}")
        c4.metric("🏷️ Tipos de Itens", f"{total_produtos_tipos} prods")
        st.divider()
        st.subheader("📈 Desempenho de Vendas")
        df_vendas['data_curta'] = df_vendas['data_hora'].str.slice(0, 10)
        df_grafico = df_vendas.groupby('data_curta')[['valor_total', 'lucro']].sum().reset_index()
        df_grafico = df_grafico.rename(columns={'data_curta': 'Data', 'valor_total': 'Faturamento (R$)', 'lucro': 'Lucro Real (R$)'})
        st.bar_chart(df_grafico.set_index('Data'), use_container_width=True)
        st.divider()
        st.markdown("### 📋 Histórico Geral de Vendas")
        st.dataframe(df_vendas[['data_hora', 'produto', 'quantidade', 'valor_total', 'lucro', 'pagamento']].rename(columns={'data_hora': 'Data/Hora', 'produto': 'Item', 'quantidade': 'Qtd Vendida', 'valor_total': 'Total (R$)', 'lucro': 'Lucro (R$)', 'pagamento': 'Pagamento'}), use_container_width=True)
