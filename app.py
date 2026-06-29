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
        # Garante a existência da coluna de código de barras caso não tenha rodado no SQL Editor
        session.execute(text("ALTER TABLE estoque ADD COLUMN IF NOT EXISTS codigo_barras VARCHAR(50);"))
        session.commit()
except Exception as e:
    st.error(f"Erro ao inicializar conexão com o banco: {e}")

# Inicializa variáveis de controle do leitor e do carrinho
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
# TELA 1: FRENTE DE CAIXA (COM SUPORTE A LEITOR)
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
            
            # 🏷️ CAMPO DO LEITOR DE CÓDIGO DE BARRAS AUTOMÁTICO
            bipe_leitor = st.text_input("🚨 BIPAR PRODUTO (Deixe o cursor aqui para usar o leitor)", key="leitor_caixa", placeholder="Passe o produto no leitor...")
            
            # Se algo foi bipado, tenta processar imediatamente
            if bipe_leitor:
                # Procura o produto correspondente ao código bipado
                prod_bipado = df_est[df_est['codigo_barras'] == bipe_leitor.strip()]
                
                if not prod_bipado.empty:
                    detalhes_bip = prod_bipado.iloc[0]
                    nome_bip = detalhes_bip['produto']
                    unidades_pack_bip = int(detalhes_bip['unidades_por_pacote'])
                    
                    # Verifica se há estoque disponível
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
                                "produto": nome_bip,
                                "quantidade": 1,
                                "preco_venda": float(detalhes_bip['preco_venda']),
                                "custo_total": custo_calculado,
                                "unidades_totais": unidades_pack_bip,
                                "subtotal": float(detalhes_bip['preco_venda'])
                            })
                        st.toast(f"✅ {nome_bip} adicionado ao carrinho!", icon="🛒")
                    else:
                        st.error(f"🚨 Produto '{nome_bip}' está esgotado no estoque!")
                else:
                    st.error(f"🔍 Código '{bipe_leitor}' não encontrado no cadastro!")
                
                # Reseta o campo para o próximo bipe
                st.session_state.leitor_caixa = ""
                st.rerun()

            st.markdown("---")
            st.caption("Ou busque manualmente por digitação se preferir:")
            
            produtos_disponiveis = df_est[df_est['quantidade'] > 0]['produto'].tolist()
            prod_selecionado = st.selectbox("Selecione Manualmente", options=produtos_disponiveis, index=None, placeholder="🔍 Digite para buscar...")
            
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
                                if detalhes['tipo_venda'] == "Fardo/Fechado":
                                    item['custo_total'] = float(detalhes['custo']) * item['quantidade']
                                else:
                                    item['custo_total'] = (float(detalhes['custo']) / unidades_pack) * item['unidades_totais']
                                ja_no_carrinho = True
                            else:
                                st.error("Quantidade excede o estoque disponível!")
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
                    st.caption("Nenhum cliente cadastrado.")
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
        df_clientes = df_clientes[df_clientes["nome"].str.contains(busca_cli, case=False, na=False) | df_clientes["bairro"].str.contains(busca_cli, case=False, na=False)]
    st.subheader("📋 Clientes Registrados")
    if not df_clientes.empty:
        st.dataframe(df_clientes[['nome', 'whatsapp', 'endereco', 'bairro', 'observacoes']].rename(columns={'nome': 'Nome do Cliente', 'whatsapp': 'WhatsApp/Celular', 'endereco': 'Endereço', 'bairro': 'Bairro', 'observacoes': 'Notas/Obs'}), use_container_width=True)
    else:
        st.info("Nenhum cliente cadastrado.")
    st.divider()
    st.subheader("➕ Registrar Novo Cliente")
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
                st.success(f"Cliente '{c_nome}' cadastrado!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

# -----------------------------------------------------------------------------------------
# TELA 3: CONTROLE DE ESTOQUE (COM CAMPO DE CÓDIGO DE BARRAS)
# -----------------------------------------------------------------------------------------
elif tela == "📦 Controle de Estoque":
    st.title("📦 Controle de Estoque Profissional")
    try:
        df_estoque = conn.query("SELECT * FROM estoque ORDER BY produto;", ttl="0s")
    except Exception as e:
        st.error(f"Erro ao carregar estoque: {e}")
        df_estoque = pd.DataFrame()

    busca = st.text_input("🔍 Buscar produto manualmente", placeholder="Digite o nome do produto...")
    if busca and not df_estoque.empty:
        df_estoque = df_estoque[df_estoque["produto"].str.contains(busca, case=False, na=False)]

    st.subheader("📋 Estoque Atual")
    if not df_estoque.empty:
        # Exibe também a coluna de código de barras para controle visual
        df_exibicao = df_estoque[['produto', 'codigo_barras', 'preco_venda', 'quantidade', 'tipo_venda']].copy()
        df_exibicao['preco_venda'] = df_exibicao['preco_venda'].map(lambda x: f"R$ {float(x):.2f}")
        df_exibicao['codigo_barras'] = df_exibicao['codigo_barras'].fillna("Não Cadastrado")
        
        df_exibicao = df_exibicao.rename(columns={'produto': 'Nome do Produto', 'codigo_barras': 'Código de Barras', 'preco_venda': 'Preço de Venda', 'quantidade': 'Qtd em Estoque', 'tipo_venda': 'Modo de Venda'})
        st.dataframe(df_exibicao, use_container_width=True)

    st.divider()

    st.subheader("➕ Cadastrar ou Atualizar Produto")
    with st.form("cadastro_produto"):
        nome = st.text_input("Nome do Produto")
        
        # 🚨 NOVO CAMPO: SÓ CLICAR AQUI E BIPAR!
        cod_barras = st.text_input("🏷️ Código de Barras (Clique aqui e bipe o produto)")
        
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
            st.info(f"📊 Custo Unitário: R$ {custo_unitario:.2f} | Lucro por Unidade: R$ {lucro_unitario:.2f} | Margem: {margem_calculada:.1f}%")

        if salvar and nome:
            preco_venda_final = round(float(preco_venda_desejado), 2)
            unidades_totais = int(quantidade * pack)
            val_cod = cod_barras.strip() if cod_barras else None

            try:
                with conn.session as session:
                    res = session.execute(text("SELECT quantidade FROM estoque WHERE produto = :p;"), {"p": nome}).fetchone()
                    est_anterior = res[0] if res else 0
                    est_novo = est_anterior + unidades_totais
                    
                    session.execute(text("""
                        INSERT INTO estoque (produto, custo, preco_venda, quantidade, unidades_por_pacote, tipo_venda, codigo_barras)
                        VALUES (:produto, :custo, :preco, :qtd, :pack, :tipo, :cod)
                        ON CONFLICT (produto)
                        DO UPDATE SET custo = :custo, preco_venda = :preco, quantidade = estoque.quantidade + :qtd, unidades_por_pacote = :pack, tipo_venda = :tipo, codigo_barras = :cod;
                        """), {"produto": nome, "custo": custo, "preco": preco_venda_final, "qtd": unidades_totais, "pack": pack, "tipo": tipo, "cod": val_cod})
                    registrar_movimentacao(session, nome, "ENTRADA", unidades_totais, est_anterior, est_novo, "Entrada de mercadoria/Cadastro")
                    session.commit()
                st.success(f"Produto '{nome}' salvo com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

    st.divider()
    # Seções de Ajuste manual e Exclusão continuam abaixo de forma idêntica
    if not df_estoque.empty:
        st.subheader("✏️ Ajustar Estoque ou Preço Manualmente")
        produto_ajuste = st.selectbox("Selecione o Produto para ajustar", df_estoque["produto"].tolist(), key="ajuste_produto")
        dados_prod = df_estoque[df_estoque["produto"] == produto_ajuste].iloc[0]
        qtd_atual = int(dados_prod["quantidade"])
        preco_atual = float(dados_prod["preco_venda"])
        
        col_aj1, col_aj2 = st.columns(2)
        with col_aj1:
            nova_qtd = st.number_input("Nova Quantidade Exata em Estoque", min_value=0, value=qtd_atual)
        with col_aj2:
            novo_preco = st.number_input("Novo Preço de Venda (R$)", min_value=0.0, value=preco_atual, step=0.01)
            
        if st.button("Salvar Ajustes"):
            try:
                preco_final_ajustado = round(float(novo_preco), 2)
                with conn.session as session:
                    session.execute(text("UPDATE estoque SET quantidade = :qtd, preco_venda = :preco WHERE produto = :produto"), {"qtd": nova_qtd, "preco": preco_final_ajustado, "produto": produto_ajuste})
                    registrar_movimentacao(session, produto_ajuste, "AJUSTE", (nova_qtd - qtd_atual), qtd_atual, nova_qtd, f"Ajuste manual. Qtd: {qtd_atual}->{nova_qtd}, Preço: {preco_atual}->{preco_final_ajustado}")
                    session.commit()
                st.success("Alterações salvas!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
                
    st.divider()
    if not df_estoque.empty:
        st.subheader("📝 Corrigir Nome do Produto (Erros de Digitação)")
        produto_nome_antigo = st.selectbox("Selecione o produto com nome errado", df_estoque["produto"].tolist(), key="nome_errado_produto")
        novo_nome_correto = st.text_input("Digite o Nome Correto do Produto", value=produto_nome_antigo)
        if st.button("💾 Confirmar Correção do Nome"):
            if novo_nome_correto.strip() != "" and novo_nome_correto != produto_nome_antigo:
                try:
                    with conn.session as session:
                        session.execute(text("UPDATE estoque SET produto = :novo WHERE produto = :antigo;"), {"novo": novo_nome_correto, "antigo": produto_nome_antigo})
                        session.execute(text("UPDATE vendas SET produto = :novo WHERE produto = :antigo;"), {"novo": novo_nome_correto, "antigo": produto_nome_antigo})
                        session.execute(text("UPDATE movimentacoes_estoque SET produto = :novo WHERE produto = :antigo;"), {"novo": novo_nome_correto, "antigo": produto_nome_antigo})
                        session.commit()
                    st.success("Nome corrigido!")
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
                    registrar_movimentacao(session, produto_excluir, "EXCLUIR", qtd_antes_del, qtd_antes_del, 0, "Deletado")
                    session.commit()
                st.success("Produto excluído!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

# --- TELA 4: EXTRATO ---
elif tela == "📋 Extrato do Estoque":
    st.title("📋 Extrato e Auditoria de Estoque")
    try:
        df_mov = conn.query("SELECT data_hora, produto, tipo_movimentacao, quantidade, estoque_anterior, estoque_novo, observacao FROM movimentacoes_estoque ORDER BY id DESC;", ttl="0s")
    except:
        df_mov = pd.DataFrame()
    if df_mov.empty:
        st.info("Nenhum histórico encontrado.")
    else:
        df_mov_friendly = df_mov.rename(columns={'data_hora': 'Data/Hora', 'produto': 'Produto', 'tipo_movimentacao': 'Operação', 'quantidade': 'Qtd Movimentada', 'estoque_anterior': 'Estoque Antigo', 'estoque_novo': 'Estoque Novo', 'observacao': 'Detalhes'})
        st.dataframe(df_mov_friendly, use_container_width=True)

# --- TELA 5: FINANCEIRO ---
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
            custo_unitario = float(row['custo']) / u_pack if row['tipo_venda'] == "Fardo/Fechado" else float(row['custo'])
            valor_estoque_custo += (custo_unitario * int(row['quantidade']))
    try:
        df_vendas = conn.query("SELECT * FROM vendas ORDER BY id DESC;", ttl="0s")
    except:
        df_vendas = pd.DataFrame()
        
    if df_vendas.empty:
        st.info("Nenhuma venda cadastrada.")
        if valor_estoque_custo > 0:
            st.metric("📦 Capital Empatado em Estoque (Preço de Custo)", f"R$ {valor_estoque_custo:.2f}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Faturamento Bruto", f"R$ {df_vendas['valor_total'].sum():.2f}")
        c2.metric("📈 Lucro Líquido Real", f"R$ {df_vendas['lucro'].sum():.2f}")
        c3.metric("📦 Valor em Estoque (Custo)", f"R$ {valor_estoque_custo:.2f}")
        c4.metric("🏷️ Tipos de Itens", f"{total_produtos_tipos} prods")
        st.divider()
        df_vendas['data_curta'] = df_vendas['data_hora'].astype(str).str.slice(0, 10)
        df_grafico = df_vendas.groupby('data_curta')[['valor_total', 'lucro']].sum().reset_index()
        df_grafico = df_grafico.rename(columns={'data_curta': 'Data', 'valor_total': 'Faturamento (R$)', 'lucro': 'Lucro Real (R$)'})
        st.bar_chart(df_grafico.set_index('Data'), use_container_width=True)
        st.divider()
        st.dataframe(df_vendas[['data_hora', 'produto', 'quantidade', 'valor_total', 'lucro', 'pagamento']].rename(columns={'data_hora': 'Data/Hora', 'produto': 'Item', 'quantidade': 'Qtd Vendida', 'valor_total': 'Total (R$)', 'lucro': 'Lucro (R$)', 'pagamento': 'Pagamento'}), use_container_width=True)
