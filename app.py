import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import text
import urllib.parse

st.set_page_config(page_title="Frios & Geladão do Reginaldo", page_icon="🏪", layout="wide")

# --- CONEXÃO COM O POSTGRESQL (SUPABASE) ---
try:
    conn = st.connection("postgresql", type="sql")
    
    # 🛡️ GARANTIA: Garante que as tabelas necessárias existem
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
        session.execute(text("ALTER TABLE estoque ADD COLUMN IF NOT EXISTS codigo_barras VARCHAR(50);"))
        session.commit()
except Exception as e:
    st.error(f"Erro ao inicializar conexão com o banco: {e}")

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

# --- MENU LATERAL ---
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
            bipe_leitor = st.text_input("🚨 BIPAR PRODUTO (Deixe o cursor aqui)", key="leitor_caixa", placeholder="Passe o produto no leitor...")
            
            if bipe_leitor:
                prod_bipado = df_est[df_est['codigo_barras'] == bipe_leitor.strip()]
                if not prod_bipado.empty:
                    detalhes_bip = prod_bipado.iloc[0]
                    nome_bip = detalhes_bip['produto']
                    unidades_pack_bip = int(detalhes_bip['unidades_por_pacote'])
                    
                    if detalhes_bip['quantidade'] > 0:
                        ja_no_carrinho = False
                        for item in st.session_state.carrinho:
                            if item['produto'] == nome_bip:
                                item['quantidade'] += 1
                                item['subtotal'] = item['quantidade'] * float(detalhes_bip['preco_venda'])
                                item['unidades_totais'] = item['quantidade'] * unidades_pack_bip
                                item['custo_total'] = (float(detalhes_bip['custo']) / unidades_pack_bip) * item['unidades_totais']
                                ja_no_carrinho = True
                        
                        if not ja_no_carrinho:
                            custo_calculado = (float(detalhes_bip['custo']) / unidades_pack_bip) * unidades_pack_bip
                            st.session_state.carrinho.append({
                                "produto": nome_bip, "quantidade": 1, "preco_venda": float(detalhes_bip['preco_venda']),
                                "custo_total": custo_calculado, "unidades_totais": unidades_pack_bip, "subtotal": float(detalhes_bip['preco_venda'])
                            })
                        st.toast(f"✅ {nome_bip} no carrinho!", icon="🛒")
                    else:
                        st.error(f"🚨 Produto '{nome_bip}' esgotado!")
                else:
                    st.error(f"🔍 Código '{bipe_leitor}' não cadastrado!")
                st.session_state.leitor_caixa = ""
                st.rerun()

            st.markdown("---")
            produtos_disponiveis = df_est[df_est['quantidade'] > 0]['produto'].tolist()
            prod_selecionado = st.selectbox("Ou selecione manualmente:", options=produtos_disponiveis, index=None, placeholder="🔍 Digite para buscar...")
            
            if prod_selecionado:
                detalhes = df_est[df_est['produto'] == prod_selecionado].iloc[0]
                unidades_pack = int(detalhes['unidades_por_pacote'])
                qtd_maxima = int(detalhes['quantidade'] // unidades_pack) if detalhes['tipo_venda'] == "Fardo/Fechado" else int(detalhes['quantidade'])
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Preço", f"R$ {float(detalhes['preco_venda']):.2f}")
                c2.metric("Estoque Atual", f"{qtd_maxima} fardos" if detalhes['tipo_venda'] == "Fardo/Fechado" else f"{qtd_maxima} un")
                c3.metric("Tipo de Venda", str(detalhes['tipo_venda']))
                
                qtd_venda = st.number_input("Quantidade desejada", min_value=1, max_value=max(1, qtd_maxima), value=1, step=1)
                
                if st.button("➕ Adicionar Manualmente"):
                    ja_no_carrinho = False
                    for item in st.session_state.carrinho:
                        if item['produto'] == prod_selecionado:
                            if item['quantidade'] + qtd_venda <= qtd_maxima:
                                item['quantidade'] += qtd_venda
                                item['subtotal'] = item['quantidade'] * float(detalhes['preco_venda'])
                                item['unidades_totais'] = item['quantidade'] * unidades_pack
                                item['custo_total'] = float(detalhes['custo']) * item['quantidade'] if detalhes['tipo_venda'] == "Fardo/Fechado" else (float(detalhes['custo']) / unidades_pack) * item['unidades_totais']
                                ja_no_carrinho = True
                            else:
                                st.error("Estoque insuficiente!")
                                ja_no_carrinho = True
                    
                    if not ja_no_carrinho:
                        custo_calculado = float(detalhes['custo']) * qtd_venda if detalhes['tipo_venda'] == "Fardo/Fechado" else (float(detalhes['custo']) / unidades_pack) * (qtd_venda * unidades_pack)
                        st.session_state.carrinho.append({
                            "produto": prod_selecionado, "quantidade": qtd_venda, "preco_venda": float(detalhes['preco_venda']),
                            "custo_total": custo_calculado, "unidades_totais": qtd_venda * unidades_pack, "subtotal": qtd_venda * float(detalhes['preco_venda'])
                        })
                    st.rerun()

        with col_carrinho:
            st.markdown("### 📋 Carrinho de Compras")
            if not st.session_state.carrinho:
                st.info("O carrinho está vazio.")
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
                st.dataframe(df_cart[['produto', 'quantidade', 'subtotal']].rename(columns={'produto': 'Item', 'quantidade': 'Qtd', 'subtotal': 'Subtotal (R$)'}), use_container_width=True)
                total_geral = df_cart['subtotal'].sum()
                st.markdown(f"""<div class="total-card"><p style="margin:0;">TOTAL DO PEDIDO</p><h2 style="margin:0;color:#2e7d32;">R$ {total_geral:.2f}</h2></div>""", unsafe_allow_html=True)
                
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
                                session.execute(text("UPDATE estoque SET quantidade = :novo WHERE produto = :prod;"), {"novo": novo_estoque, "prod": item['produto']})
                                lucro_item = item['subtotal'] - item['custo_total']
                                session.execute(text("INSERT INTO vendas (data_hora, produto, quantidade, valor_total, lucro, pagamento) VALUES (:dt, :prod, :qtd, :val, :luc, :pag);"), {"dt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "prod": item['produto'], "qtd": item['quantidade'], "val": item['subtotal'], "luc": lucro_item, "pag": forma_pagamento})
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

# -----------------------------------------------------------------------------------------
# TELA 2: CADASTRO DE CLIENTES
# -----------------------------------------------------------------------------------------
elif tela == "👥 Cadastro de Clientes":
    st.title("👥 Gestão e Cadastro de Clientes")
    try:
        df_clientes = conn.query("SELECT * FROM clientes ORDER BY nome;", ttl="0s")
    except Exception as e:
        st.error(f"Erro ao carregar clientes: {e}")
        df_clientes = pd.DataFrame()
    busca_cli = st.text_input("🔍 Buscar Cliente", placeholder="Digite o nome...")
    if busca_cli and not df_clientes.empty:
        df_clientes = df_clientes[df_clientes["nome"].str.contains(busca_cli, case=False, na=False)]
    st.subheader("📋 Clientes Registrados")
    if not df_clientes.empty:
        st.dataframe(df_clientes[['nome', 'whatsapp', 'endereco', 'bairro', 'observacoes']].rename(columns={'nome': 'Nome do Cliente', 'whatsapp': 'WhatsApp/Celular', 'endereco': 'Endereço', 'bairro': 'Bairro', 'observacoes': 'Notas/Obs'}), use_container_width=True)
    with st.form("cadastro_cliente"):
        c_nome = st.text_input("Nome Completo")
        c_whats = st.text_input("WhatsApp (DDD + Número)")
        c_end = st.text_input("Endereço")
        c_bairro = st.text_input("Bairro")
        c_obs = st.text_area("Observações")
        salvar_cliente = st.form_submit_button("💾 Salvar Cliente")
        if salvar_cliente and c_nome and c_whats:
            try:
                with conn.session as session:
                    session.execute(text("INSERT INTO clientes (nome, whatsapp, endereco, bairro, observacoes) VALUES (:nome, :whats, :end, :bairro, :obs);"), {"nome": c_nome, "whats": c_whats, "end": c_end, "bairro": c_bairro, "obs": c_obs})
                    session.commit()
                st.success("Cliente cadastrado!")
                st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

# -----------------------------------------------------------------------------------------
# TELA 3: CONTROLE DE ESTOQUE
# -----------------------------------------------------------------------------------------
elif tela == "📦 Controle de Estoque":
    st.title("📦 Controle de Estoque Profissional")
    try:
        df_estoque = conn.query("SELECT * FROM estoque ORDER BY produto;", ttl="0s")
    except Exception as e:
        st.error(f"Erro: {e}"); df_estoque = pd.DataFrame()

    busca = st.text_input("🔍 Buscar produto manualmente", placeholder="Digite o nome do produto...")
    if busca and not df_estoque.empty:
        df_estoque = df_estoque[df_estoque["produto"].str.contains(busca, case=False, na=False)]

    st.subheader("📋 Estoque Atual")
    if not df_estoque.empty:
        df_exibicao = df_estoque[['produto', 'codigo_barras', 'preco_venda', 'quantidade', 'tipo_venda']].copy()
        df_exibicao['preco_venda'] = df_exibicao['preco_venda'].map(lambda x: f"R$ {float(x):.2f}")
        df_exibicao['codigo_barras'] = df_exibicao['codigo_barras'].fillna("Não Cadastrado")
        st.dataframe(df_exibicao.rename(columns={'produto': 'Nome do Produto', 'codigo_barras': 'Código de Barras', 'preco_venda': 'Preço de Venda', 'quantidade': 'Qtd em Estoque', 'tipo_venda': 'Modo de Venda'}), use_container_width=True)

    st.divider()
    
    st.subheader("📥 Importar Lista de Produtos via Excel (CSV)")
    st.caption("A planilha deve conter exatamente as colunas: produto, codigo_barras, tipo_venda, unidades_por_pacote, custo, preco_venda")
    
    arquivo_upload = st.file_uploader("Selecione o arquivo .csv gerado pelo Excel", type=["csv"])
    if arquivo_upload is not None:
        try:
            df_importado = pd.read_csv(arquivo_upload)
            st.markdown("**Prévia dos produtos encontrados na sua planilha:**")
            st.dataframe(df_importado.head(5), use_container_width=True)
            
            if st.button("🚀 Confirmar e Enviar Planilha para o Banco de Dados"):
                colunas_obrigatorias = ['produto', 'tipo_venda', 'unidades_por_pacote', 'custo', 'preco_venda']
                if not all(col in df_importado.columns for col in colunas_obrigatorias):
                    st.error("🚨 Erro! Verifique se os nomes das colunas na sua planilha estão idênticos aos exigidos.")
                else:
                    contador = 0
                    with conn.session as session:
                        for _, row_plan in df_importado.iterrows():
                            cod_b = str(row_plan['codigo_barras']).strip() if 'codigo_barras' in df_importado.columns and pd.notna(row_plan['codigo_barras']) else None
                            
                            session.execute(text("""
                                INSERT INTO estoque (produto, custo, preco_venda, quantidade, unidades_por_pacote, tipo_venda, codigo_barras)
                                VALUES (:produto, :custo, :preco, 0, :pack, :tipo, :cod)
                                ON CONFLICT (produto) DO UPDATE SET custo = :custo, preco_venda = :preco, unidades_por_pacote = :pack, tipo_venda = :tipo, codigo_barras = :cod;
                            """), {
                                "produto": str(row_plan['produto']).strip(),
                                "custo": float(row_plan['custo']),
                                "preco": float(row_plan['preco_venda']),
                                "pack": int(row_plan['unidades_por_pacote']),
                                "tipo": str(row_plan['tipo_venda']).strip(),
                                "cod": cod_b
                            })
                            contador += 1
                        session.commit()
                    st.success(f"🎉 Sucesso! {contador} produtos foram importados/atualizados no estoque do banco de dados!")
                    st.rerun()
        except Exception as e_imp:
            st.error(f"Erro ao ler arquivo: {e_imp}")

    st.divider()
    st.subheader("➕ Cadastrar ou Atualizar Produto Manualmente")
    with st.form("cadastro_produto"):
        nome = st.text_input("Nome do Produto")
        cod_barras = st.text_input("🏷️ Código de Barras (Clique aqui e bipe)")
        tipo = st.selectbox("Tipo de Venda", ["Unidade Avulsa", "Fardo/Fechado"])
        pack = st.number_input("Unidades por fardo", min_value=1, value=1)
        custo = st.number_input("Preço de Custo Total (R$)", min_value=0.0, value=0.0, step=0.01)
        preco_venda_desejado = st.number_input("Preço de Venda Desejado (R$)", min_value=0.0, value=0.0, step=0.01)
        quantidade = st.number_input("Quantidade comprada", min_value=0, value=0)
        salvar = st.form_submit_button("💾 Salvar Produto")

        if custo > 0 and preco_venda_desejado > 0:
            custo_unitario = custo / pack
            lucro_unitario = preco_venda_desejado - custo_unitario
            margem_calculada = (lucro_unitario / custo_unitario) * 100 if custo_unitario > 0 else 0.0
            st.info(f"📊 Custo Unitário: R$ {custo_unitario:.2f} | Margem: {margem_calculada:.1f}%")

        if salvar and nome:
            preco_venda_final = round(float(preco_venda_desejado), 2)
            unidades_totais = int(quantidade * pack)
            try:
                with conn.session as session:
                    res = session.execute(text("SELECT quantidade FROM estoque WHERE produto = :p;"), {"p": nome}).fetchone()
                    est_anterior = res[0] if res else 0
                    session.execute(text("""
                        INSERT INTO estoque (produto, custo, preco_venda, quantidade, unidades_por_pacote, tipo_venda, codigo_barras)
                        VALUES (:produto, :custo, :preco, :qtd, :pack, :tipo, :cod)
                        ON CONFLICT (produto) DO UPDATE SET custo = :custo, preco_venda = :preco, quantidade = estoque.quantidade + :qtd, unidades_por_pacote = :pack, tipo_venda = :tipo, codigo_barras = :cod;
                        """), {"produto": nome, "custo": custo, "preco": preco_venda_final, "qtd": unidades_totais, "pack": pack, "tipo": tipo, "cod": cod_barras.strip() if cod_barras else None})
                    registrar_movimentacao(session, nome, "ENTRADA", unidades_totais, est_anterior, est_anterior + unidades_totais, "Entrada de mercadoria")
                    session.commit()
                st.success("Salvo!"); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    if not df_estoque.empty:
        st.subheader("✏️ Ajustar Estoque ou Preço Manualmente")
        produto_ajuste = st.selectbox("Selecione o Produto para ajustar", df_estoque["produto"].tolist(), key="ajuste_produto")
        dados_prod = df_estoque[df_estoque["produto"] == produto_ajuste].iloc[0]
        col_aj1, col_aj2 = st.columns(2)
        with col_aj1: 
            # 🛡️ CORREÇÃO: Garante que valores negativos não quebrem o min_value=0
            qtd_segura = max(0, int(dados_prod["quantidade"]))
            nova_qtd = st.number_input("Nova Quantidade Exata", min_value=0, value=qtd_segura)
        with col_aj2: 
            preco_seguro = max(0.0, float(dados_prod["preco_venda"]))
            novo_preco = st.number_input("Novo Preço de Venda (R$)", min_value=0.0, value=preco_seguro, step=0.01)
        if st.button("Salvar Ajustes"):
            try:
                with conn.session as session:
                    session.execute(text("UPDATE estoque SET quantidade = :qtd, preco_venda = :preco WHERE produto = :produto"), {"qtd": nova_qtd, "preco": round(float(novo_preco), 2), "produto": produto_ajuste})
                    registrar_movimentacao(session, produto_ajuste, "AJUSTE", (nova_qtd - int(dados_prod["quantidade"])), int(dados_prod["quantidade"]), nova_qtd, f"Ajuste manual. Preço antigo: R$ {dados_prod['preco_venda']}")
                    session.commit()
                st.success("Atualizado!"); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    if not df_estoque.empty:
        st.subheader("📝 Corrigir Nome do Produto")
        produto_nome_antigo = st.selectbox("Selecione o produto com nome errado", df_estoque["produto"].tolist(), key="nome_errado_produto")
        novo_nome_correto = st.text_input("Digite o Nome Correto", value=produto_nome_antigo)
        if st.button("💾 Confirmar Correção"):
            if novo_nome_correto.strip() != "" and novo_nome_correto != produto_nome_antigo:
                try:
                    with conn.session as session:
                        session.execute(text("UPDATE estoque SET produto = :novo WHERE produto = :antigo;"), {"novo": novo_nome_correto, "antigo": produto_nome_antigo})
                        session.execute(text("UPDATE vendas SET produto = :novo WHERE produto = :antigo;"), {"novo": novo_nome_correto, "antigo": produto_nome_antigo})
                        session.execute(text("UPDATE movimentacoes_estoque SET produto = :novo WHERE produto = :antigo;"), {"novo": novo_nome_correto, "antigo": produto_nome_antigo})
                        session.commit()
                    st.success("Nome corrigido!"); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    if not df_estoque.empty:
        st.subheader("🗑️ Excluir Produto")
        produto_excluir = st.selectbox("Produto para excluir", df_estoque["produto"].tolist(), key="excluir_produto")
        if st.button("Excluir Definitivamente"):
            try:
                with conn.session as session:
                    session.execute(text("DELETE FROM estoque WHERE produto = :produto"), {"produto": produto_excluir})
                    session.commit()
                st.success("Excluído!"); st.rerun()
            except Exception as e: st.error(f"Erro: {e}")

# -----------------------------------------------------------------------------------------
# TELA 4: EXTRATO DE MOVIMENTAÇÕES
# -----------------------------------------------------------------------------------------
elif tela == "📋 Extrato do Estoque":
    st.title("📋 Extrato e Auditoria de Estoque")
    try:
        df_mov = conn.query("SELECT data_hora, produto, tipo_movimentacao, quantidade, estoque_anterior, estoque_novo, observacao FROM movimentacoes_estoque ORDER BY id DESC;", ttl="0s")
    except: df_mov = pd.DataFrame()
    if df_mov.empty: st.info("Nenhum histórico.")
    else: st.dataframe(df_mov.rename(columns={'data_hora': 'Data/Hora', 'produto': 'Produto', 'tipo_movimentacao': 'Operação', 'quantidade': 'Qtd Movimentada', 'estoque_anterior': 'Estoque Antigo', 'estoque_novo': 'Estoque Novo', 'observacao': 'Detalhes'}), use_container_width=True)

# -----------------------------------------------------------------------------------------
# TELA 5: PAINEL FINANCEIRO
# -----------------------------------------------------------------------------------------
else:
    st.title("📊 Painel Financeiro & Fechamento de Inventário")
    
    try:
        df_est_fin = conn.query("SELECT produto, custo, preco_venda, quantidade, unidades_por_pacote, tipo_venda FROM estoque ORDER BY produto;", ttl="0s")
    except: df_est_fin = pd.DataFrame()
    
    valor_estoque_custo = 0.0
    valor_estoque_venda = 0.0
    total_produtos_tipos = 0
    df_inventario_print = pd.DataFrame()
    
    if not df_est_fin.empty:
        total_produtos_tipos = len(df_est_fin)
        lista_inventario = []
        for _, row in df_est_fin.iterrows():
            u_pack = int(row['unidades_por_pacote'])
            qtd_atual = int(row['quantidade'])
            custo_unitario = float(row['custo']) / u_pack if row['tipo_venda'] == "Fardo/Fechado" else float(row['custo'])
            preco_venda_unitario = float(row['preco_venda'])
            total_custo_item = custo_unitario * qtd_atual
            total_venda_item = preco_venda_unitario * qtd_atual
            
            valor_estoque_custo += total_custo_item
            valor_estoque_venda += total_venda_item
            
            lista_inventario.append({
                "Produto": row['produto'],
                "Qtd Total (un)": qtd_atual,
                "Custo Unitário (R$)": round(custo_unitario, 2),
                "Preço Venda (R$)": round(preco_venda_unitario, 2),
                "Custo Total Parado (R$)": round(total_custo_item, 2),
                "Faturamento Estimado (R$)": round(total_venda_item, 2)
            })
        df_inventario_print = pd.DataFrame(lista_inventario)

    try:
        df_vendas = conn.query("SELECT * FROM vendas ORDER BY id DESC;", ttl="0s")
    except: df_vendas = pd.DataFrame()
        
    if df_vendas.empty:
        st.info("Nenhuma venda realizada ainda para gerar os relatórios de lucro.")
        if valor_estoque_custo > 0:
            st.metric("📦 Capital Empatado em Estoque (Custo)", f"R$ {valor_estoque_custo:.2f}")
    else:
        df_vendas['data_curta'] = df_vendas['data_hora'].astype(str).str.slice(0, 10)
        
        hoje_str = datetime.now().strftime("%Y-%m-%d")
        df_hoje = df_vendas[df_vendas['data_curta'] == hoje_str]
        fat_hoje = df_hoje['valor_total'].sum() if not df_hoje.empty else 0.0
        lucro_hoje = df_hoje['lucro'].sum() if not df_hoje.empty else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("☀️ Lucro de HOJE", f"R$ {lucro_hoje:.2f}", delta=f"Vendas Hoje: R$ {fat_hoje:.2f}")
        c2.metric("📈 Lucro Total Acumulado", f"R$ {df_vendas['lucro'].sum():.2f}")
        c3.metric("💰 Faturamento Total", f"R$ {df_vendas['valor_total'].sum():.2f}")
        c4.metric("📦 Valor em Estoque (Custo)", f"R$ {valor_estoque_custo:.2f}")
        
        st.divider()
        st.subheader("📈 Desempenho e Lucro por Dia")
        
        df_grafico = df_vendas.groupby('data_curta')[['valor_total', 'lucro']].sum().reset_index()
        st.bar_chart(df_grafico.rename(columns={'data_curta': 'Data', 'valor_total': 'Faturamento (R$)', 'lucro': 'Lucro Real (R$)'}).set_index('Data'), use_container_width=True)
        
        st.divider()
        st.subheader("🗄️ Relatórios Financeiros (Passe o mouse na tabela para baixar)")
        
        tab_lucro_diario, tab_vendas_geral, tab_estoque = st.tabs([
            "📅 Relatório de Lucro Diário", 
            "📋 Histórico Geral de Vendas", 
            "📦 Inventário de Estoque"
        ])
        
        with tab_lucro_diario:
            st.markdown("**Resumo do Faturamento e Lucro por Data:**")
            df_lucro_dia = df_vendas.groupby('data_curta').agg(
                Faturamento_Dia=('valor_total', 'sum'),
                Lucro_Dia=('lucro', 'sum'),
                Qtd_Vendas=('id', 'count')
            ).reset_index().sort_values(by='data_curta', ascending=False)
            
            df_lucro_dia_exibir = df_lucro_dia.rename(columns={
                'data_curta': 'Data',
                'Faturamento_Dia': 'Faturamento (R$)',
                'Lucro_Dia': 'Lucro Líquido (R$)',
                'Qtd_Vendas': 'Número de Vendas'
            })
            
            df_lucro_dia_exibir['Faturamento (R$)'] = df_lucro_dia_exibir['Faturamento (R$)'].map(lambda x: f"R$ {x:.2f}")
            df_lucro_dia_exibir['Lucro Líquido (R$)'] = df_lucro_dia_exibir['Lucro Líquido (R$)'].map(lambda x: f"R$ {x:.2f}")
            
            st.dataframe(df_lucro_dia_exibir, use_container_width=True)
            
        with tab_vendas_geral:
            st.dataframe(df_vendas[['data_hora', 'produto', 'quantidade', 'valor_total', 'lucro', 'pagamento']].rename(columns={
                'data_hora': 'Data/Hora', 'produto': 'Item', 'quantidade': 'Qtd Vendida', 'valor_total': 'Total Recebido (R$)', 'lucro': 'Lucro Real (R$)', 'pagamento': 'Forma Pagto'
            }), use_container_width=True)
            
        with tab_estoque:
            if not df_inventario_print.empty: 
                st.dataframe(df_inventario_print, use_container_width=True)
