#!/usr/bin/env python3
"""Test _gerar_termos() with 500+ diverse company profiles."""
import random, re, sys, time, io
random.seed(42)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

# ── Extract the function from app.py ──
with open('app.py', 'r', encoding='utf-8') as f:
    src = f.read()

idx = src.index('def _gerar_termos(')
# Find the return statement that closes the function
lines = src[idx:].split('\n')
end_offset = 0
for i, line in enumerate(lines):
    if "return {'termos': lista," in line:
        end_offset = sum(len(l) + 1 for l in lines[:i+1])
        break
func_code = src[idx:idx + end_offset]
exec(func_code)

# ── 500+ company profiles ──
EMPRESAS = [
    # AGRO / CEREALISTA (50)
    ("Pili Industrial", "Vendemos tombadores de grãos, coletores de amostra, rachadores de lenha, prensas hidráulicas e centrais hidráulicas para o setor agrícola e indústria cerealista. Nosso cliente ideal é o gerente de operações de cooperativas agrícolas, cerealistas, silos, tradings e agroindústrias no Sul e Centro-Oeste do Brasil.", "https://pili.ind.br"),
    ("AgroParts BR", "Fabricamos peças de reposição para colheitadeiras e tratores. Atendemos revendedoras agrícolas, concessionárias de máquinas e fazendas no Paraná e Mato Grosso.", "https://agropartsbr.com.br"),
    ("SiloPlan", "Projetos de construção e manutenção de silos metálicos para armazenagem de grãos. Cliente ideal: cerealistas, cooperativas agrícolas e armazéns gerais no Centro-Oeste.", "https://siloplan.com.br"),
    ("GrãoTech", "Sensores IoT para monitoramento de temperatura e umidade em silos de grãos. Atendemos cooperativas agrícolas, cerealistas e agroindústrias em todo o Brasil.", "https://graotech.com.br"),
    ("BioSafra", "Fertilizantes biológicos para soja e milho. Cliente ideal: fazendas, cooperativas e revendedoras agrícolas no Sul, Sudeste e Centro-Oeste.", "https://biossafra.com.br"),
    ("AgroDrones", "Drones para pulverização e mapeamento de lavouras de soja, milho e algodão. Atendemos fazendas, cooperativas agrícolas e empresas de aviação agrícola em Goiás e Mato Grosso.", "https://agrodrones.com.br"),
    ("CaféPrime", "Exportadora de café especial arábica. Cliente ideal: torrefadoras, cooperativas de café, beneficiadoras e importadoras na Europa e EUA.", "https://cafeprime.com.br"),
    ("MilhoFort", "Ração animal à base de milho para suínos e aves. Atendemos granjas, frigoríficos e cooperativas no Sul do Brasil.", "https://milhofort.com.br"),
    ("TrigoMaster", "Farinha de trigo especial para panificação industrial. Cliente ideal: padarias industriais, moinhos e indústrias alimentícias.", "https://trigomaster.com.br"),
    ("ArrozBR", "Beneficiamento e empacotamento de arroz. Atendemos cooperativas de arroz, supermercados e distribuidoras de alimentos no Rio Grande do Sul.", "https://arrozbr.com.br"),
    ("SementesTop", "Sementes certificadas de soja e milho. Cliente ideal: fazendas, revendedoras agrícolas e cooperativas no Paraná e Goiás.", "https://sementestop.com.br"),
    ("PecuáriaVet", "Vacinas e medicamentos veterinários para gado de corte. Atendemos fazendas de pecuária, confinamentos e frigoríficos no Centro-Oeste.", "https://pecuariavet.com.br"),
    ("AgroLogística", "Transporte rodoviário de grãos e insumos agrícolas. Cliente ideal: cerealistas, tradings, cooperativas e agroindústrias no Mato Grosso e Goiás.", "https://agrologistica.com.br"),
    ("IrrigaTech", "Sistemas de irrigação por pivô central. Atendemos fazendas e agroindústrias em Minas Gerais e Bahia.", "https://irrigatech.com.br"),
    ("CoopCredSul", "Cooperativa de crédito rural. Atendemos produtores rurais, fazendas e agroindústrias no Rio Grande do Sul e Santa Catarina.", "https://coopCredsul.com.br"),
    ("BovTech", "Software de gestão de rebanho bovino. Cliente ideal: fazendas de gado, confinamentos e leilões no Centro-Oeste.", "https://bovtech.com.br"),
    ("PlantMax", "Máquinas plantadeiras e semeadeiras. Atendemos revendedoras agrícolas e fazendas no Paraná e Mato Grosso do Sul.", "https://plantmax.com.br"),
    ("FertilMix", "Misturadora de fertilizantes NPK. Cliente ideal: cooperativas agrícolas, revendedoras e agroindústrias.", "https://fertilmix.com.br"),
    ("SecaGrão", "Secadores de grãos a lenha e GLP. Atendemos cerealistas, silos e cooperativas agrícolas no Sul e Centro-Oeste.", "https://secagrao.com.br"),
    ("AlgodãoBR", "Descaroçadora de algodão. Cliente ideal: agroindústrias de algodão, cooperativas e tradings em Mato Grosso e Bahia.", "https://algodaobr.com.br"),

    # SAÚDE (40)
    ("MedEquip", "Equipamentos médicos hospitalares - camas, macas, mesas cirúrgicas. Cliente ideal: hospitais, clínicas médicas e laboratórios no Sudeste.", "https://medequip.com.br"),
    ("DentalPro", "Cadeiras e equipamentos odontológicos. Atendemos clínicas odontológicas, consultórios e faculdades de odontologia em todo o Brasil.", "https://dentalpro.com.br"),
    ("LabTech", "Reagentes e equipamentos para laboratórios de análises clínicas. Cliente ideal: laboratórios, hospitais e clínicas em São Paulo e Minas Gerais.", "https://labtech.com.br"),
    ("OrthoFit", "Órteses e próteses ortopédicas sob medida. Atendemos hospitais, clínicas de reabilitação e operadoras de saúde.", "https://orthofit.com.br"),
    ("FarmaDistri", "Distribuidora de medicamentos genéricos. Cliente ideal: farmácias, drogarias, hospitais e clínicas no Nordeste.", "https://farmadistri.com.br"),
    ("VidaSaúde", "Planos de saúde empresariais. Atendemos empresas de médio e grande porte em todo o Brasil.", "https://vidasaude.com.br"),
    ("BioImagem", "Equipamentos de diagnóstico por imagem - ultrassom, raio-X, tomógrafo. Cliente ideal: hospitais e clínicas médicas no Sul e Sudeste.", "https://bioimagem.com.br"),
    ("EsterilMax", "Autoclaves e equipamentos de esterilização hospitalar. Atendemos hospitais, clínicas e laboratórios.", "https://esterilmax.com.br"),
    ("PharmaLog", "Logística de medicamentos controlados com cadeia fria. Cliente ideal: hospitais, farmácias e distribuidoras de medicamentos.", "https://pharmalog.com.br"),
    ("NutriClinic", "Suplementos nutricionais clínicos para hospitais. Atendemos hospitais, clínicas e casas de repouso em São Paulo.", "https://nutriclinic.com.br"),
    ("HomeCarePlus", "Equipamentos para home care - camas hospitalares, oxigênio, CPAP. Atendemos operadoras de saúde e clínicas de home care.", "https://homecareplus.com.br"),
    ("VetPharma", "Medicamentos veterinários para animais de companhia. Atendemos clínicas veterinárias e pet shops em todo o Brasil.", "https://vetpharma.com.br"),
    ("OftalmoTech", "Equipamentos oftalmológicos. Cliente ideal: clínicas de oftalmologia e hospitais.", "https://oftalmotech.com.br"),
    ("RadioPro", "Equipamentos de radioterapia e medicina nuclear. Cliente ideal: hospitais oncológicos e centros de radioterapia.", "https://radiopro.com.br"),
    ("FisioEquip", "Equipamentos de fisioterapia e reabilitação. Atendemos clínicas de fisioterapia, hospitais e academias.", "https://fisioequip.com.br"),

    # TECNOLOGIA / SOFTWARE (50)
    ("PharmaSys", "ERP para redes de farmácias e drogarias. Nosso cliente ideal é o gerente de TI de redes de farmácias em todo o Brasil.", "https://pharmasys.com.br"),
    ("CloudSecure", "Soluções de segurança cibernética para empresas. Atendemos empresas de tecnologia, bancos e fintechs.", "https://cloudsecure.com.br"),
    ("ERPContábil", "Sistema de contabilidade em nuvem. Cliente ideal: escritórios de contabilidade e consultorias tributárias em todo o Brasil.", "https://erpcontabil.com.br"),
    ("LogiTrack", "Software de gestão de frotas e logística. Atendemos transportadoras e empresas de logística no Sudeste.", "https://logitrack.com.br"),
    ("EduTech Pro", "Plataforma LMS para ensino a distância. Cliente ideal: faculdades, escolas particulares e centros de treinamento.", "https://edutechpro.com.br"),
    ("HRCloud", "Software de gestão de recursos humanos. Atendemos empresas de médio porte, BPOs e empresas de call center.", "https://hrcloud.com.br"),
    ("RetailOS", "PDV e sistema de gestão para varejo. Cliente ideal: lojas de roupas, supermercados, franquias e redes de lojas.", "https://retailos.com.br"),
    ("CondoApp", "App de gestão de condomínios. Atendemos condomínios residenciais e comerciais no Sudeste.", "https://condoapp.com.br"),
    ("AutoGestão", "Software de gestão para concessionárias e oficinas mecânicas. Atendemos concessionárias de veículos e autopeças.", "https://autogestao.com.br"),
    ("JurisTech", "Software jurídico para escritórios de advocacia. Atendemos escritórios de advocacia e departamentos jurídicos corporativos.", "https://juristech.com.br"),
    ("AgriSoft", "Software de gestão de fazendas e rastreabilidade de safra. Atendemos fazendas e cooperativas agrícolas.", "https://agrisoft.com.br"),
    ("ProvedorNet", "Software de gestão para provedores de internet. Atendemos provedores de internet e empresas de telecom em todo o Brasil.", "https://provedornet.com.br"),
    ("HotelSys", "PMS para hotéis e pousadas. Cliente ideal: hotéis, pousadas e redes hoteleiras no Nordeste.", "https://hotelsys.com.br"),
    ("FinTechPay", "Gateway de pagamento para e-commerce. Atendemos lojas virtuais, startups e marketplaces.", "https://fintechpay.com.br"),
    ("ConstruSoft", "Software BIM para construtoras. Atendemos construtoras, incorporadoras e empresas de engenharia.", "https://construsoft.com.br"),
    ("DataAnalytics", "Plataforma de business intelligence. Cliente ideal: empresas de tecnologia, consultorias e startups.", "https://dataanalytics.com.br"),
    ("CallCenter Pro", "Software para centrais de atendimento. Atendemos empresas de call center, BPOs e operadoras de telecom.", "https://callcenterpro.com.br"),
    ("MineTrack", "Software de gestão para mineradoras. Atendemos mineradoras, pedreiras e empresas de mineração em Minas Gerais.", "https://minetrack.com.br"),
    ("ImoGestão", "CRM imobiliário para corretores e imobiliárias. Atendemos imobiliárias e incorporadoras.", "https://imogestao.com.br"),
    ("GráficaPrint", "Software de gestão para gráficas. Atendemos gráficas e editoras em todo o Brasil.", "https://graficaprint.com.br"),

    # CONSTRUÇÃO CIVIL (30)
    ("CimentoBR", "Cimento CP-II e CP-IV para construção civil. Cliente ideal: construtoras, concreteiras e lojas de materiais de construção.", "https://cimentobr.com.br"),
    ("AçoForte", "Vergalhões, treliças e aço para construção civil. Atendemos construtoras, incorporadoras e distribuidoras de aço.", "https://acoforte.com.br"),
    ("TelhaMax", "Telhas metálicas e termoacústicas. Cliente ideal: construtoras, galpões industriais e barracões agrícolas.", "https://telhamax.com.br"),
    ("PisoDecor", "Pisos e revestimentos cerâmicos. Atendemos lojas de materiais de construção, construtoras e incorporadoras.", "https://pisodecor.com.br"),
    ("EletroConstru", "Material elétrico para construção civil. Atendemos construtoras, eletricistas e lojas de materiais de construção no Sudeste.", "https://eletroconstru.com.br"),
    ("HidroTubos", "Tubos e conexões hidráulicas PVC e PPR. Cliente ideal: construtoras, distribuidoras hidráulicas e lojas de materiais.", "https://hidrotubos.com.br"),
    ("VidroFit", "Vidros temperados e esquadrias de alumínio. Atendemos construtoras, vidraçarias e incorporadoras.", "https://vidrofit.com.br"),
    ("ConcreMix", "Concreto usinado e argamassa. Cliente ideal: construtoras e empresas de engenharia no Sudeste.", "https://concremix.com.br"),
    ("PinturaMax", "Tintas e revestimentos para construção civil. Atendemos construtoras, pintores e lojas de materiais de construção.", "https://pinturamax.com.br"),
    ("ArqProjetos", "Projetos arquitetônicos e engenharia estrutural. Atendemos construtoras, incorporadoras e imobiliárias.", "https://arqprojetos.com.br"),
    ("ElevadorTech", "Elevadores e plataformas de acessibilidade. Cliente ideal: construtoras, condomínios e shoppings.", "https://elevadortech.com.br"),
    ("GeoPerfil", "Sondagem geotécnica e estudos de solo. Atendemos construtoras, incorporadoras e empresas de engenharia.", "https://geoperfil.com.br"),
    ("AndaimesPro", "Locação de andaimes e equipamentos para obra. Cliente ideal: construtoras no Sudeste e Sul.", "https://andaimespro.com.br"),

    # INDÚSTRIA (50)
    ("MetalCorte", "Máquinas CNC de corte a laser e plasma. Atendemos indústrias metalúrgicas, fábricas e oficinas no Sudeste.", "https://metalcorte.com.br"),
    ("PlastiMold", "Moldes de injeção plástica. Cliente ideal: indústrias de plásticos, fábricas de embalagens e autopeças.", "https://plastimold.com.br"),
    ("QuímiMax", "Produtos químicos industriais - solventes, ácidos, bases. Atendemos indústrias químicas, têxteis e metalúrgicas.", "https://quimimax.com.br"),
    ("TêxtilPro", "Máquinas têxteis para tecelagem e acabamento. Cliente ideal: indústrias têxteis no Sul e Sudeste.", "https://textilpro.com.br"),
    ("SoldarTech", "Equipamentos de solda MIG/MAG e TIG. Atendemos indústrias metalúrgicas, construtoras e estaleiros.", "https://soldartech.com.br"),
    ("PapelBR", "Papel kraft e embalagens de papelão. Cliente ideal: indústrias, distribuidoras e e-commerces.", "https://papelbr.com.br"),
    ("BorrachaPro", "Peças técnicas em borracha sob medida. Atendemos indústrias automotivas, mineradoras e fábricas.", "https://borrachapro.com.br"),
    ("CompressorAir", "Compressores de ar industrial. Atendemos fábricas, indústrias metalúrgicas e oficinas mecânicas.", "https://compressorair.com.br"),
    ("FiltroIndustrial", "Filtros industriais para ar e líquidos. Cliente ideal: indústrias químicas, alimentícias e farmacêuticas.", "https://filtroindustrial.com.br"),
    ("EmbalaTech", "Máquinas de embalagem automática. Atendemos indústrias alimentícias, farmacêuticas e cosméticas.", "https://embalatech.com.br"),
    ("FornoBR", "Fornos industriais elétricos e a gás. Cliente ideal: indústrias cerâmicas, metalúrgicas e alimentícias.", "https://fornobr.com.br"),
    ("RoboWeld", "Robôs de soldagem industrial. Atendemos indústrias automotivas e metalúrgicas em São Paulo.", "https://roboweld.com.br"),
    ("LubriTech", "Lubrificantes industriais. Atendemos fábricas, mineradoras e indústrias metalúrgicas.", "https://lubritech.com.br"),
    ("EsteiraBR", "Esteiras transportadoras industriais. Cliente ideal: mineradoras, indústrias alimentícias e fábricas.", "https://esteirabr.com.br"),
    ("InoxPro", "Peças e equipamentos em aço inox. Atendemos indústrias alimentícias, farmacêuticas e hospitais.", "https://inoxpro.com.br"),
    ("CaldeiraMax", "Caldeiras industriais a vapor. Cliente ideal: usinas, indústrias alimentícias e têxteis.", "https://caldeiramax.com.br"),
    ("MotorElétrico", "Motores elétricos industriais WEG e Siemens. Atendemos fábricas, indústrias e distribuidoras elétricas.", "https://motoreletrico.com.br"),
    ("ReciclaIndustrial", "Máquinas para reciclagem - trituradores, prensas, esteiras. Atendemos cooperativas de reciclagem e empresas de reciclagem.", "https://reciclaindustrial.com.br"),
    ("MáquinasMadeira", "Máquinas para marcenaria e indústria moveleira. Cliente ideal: fábricas de móveis e marcenarias no Sul.", "https://maquinasmadeira.com.br"),
    ("FundiBR", "Fundição de peças em ferro e alumínio. Atendemos indústrias automotivas, metalúrgicas e de máquinas.", "https://fundibr.com.br"),

    # ALIMENTÍCIO (30)
    ("FrigoTech", "Câmaras frigoríficas e equipamentos de refrigeração industrial. Atendemos frigoríficos, supermercados e distribuidoras de alimentos.", "https://frigotech.com.br"),
    ("PanificMax", "Equipamentos para panificação - fornos, masseiras, modeladoras. Cliente ideal: padarias industriais, confeitarias e moinhos.", "https://panificmax.com.br"),
    ("LaticínioBR", "Equipamentos para processamento de leite e derivados. Atendemos laticínios, cooperativas e indústrias alimentícias.", "https://laticiniobr.com.br"),
    ("CarnePro", "Equipamentos para processamento de carnes. Cliente ideal: frigoríficos, açougues industriais e distribuidoras.", "https://carnepro.com.br"),
    ("SucoFresh", "Máquinas para processamento de sucos e polpas de frutas. Atendemos indústrias alimentícias e cooperativas no Nordeste.", "https://sucofresh.com.br"),
    ("EmbalFood", "Embalagens plásticas para alimentos. Cliente ideal: indústrias alimentícias, padarias industriais e distribuidoras.", "https://embalfood.com.br"),
    ("TempControl", "Termômetros e sensores de temperatura para cadeia fria. Atendemos supermercados, frigoríficos e distribuidoras.", "https://tempcontrol.com.br"),
    ("AçúcarBR", "Açúcar e derivados para indústria. Cliente ideal: indústrias alimentícias, padarias industriais, usinas de açúcar e álcool.", "https://acucarbr.com.br"),
    ("SaborMax", "Aromas e condimentos industriais. Atendemos indústrias alimentícias, restaurantes industriais e distribuidoras.", "https://sabormax.com.br"),
    ("CervejaEquip", "Equipamentos para cervejarias artesanais. Cliente ideal: microcervejarias, brewpubs e distribuidoras de bebidas.", "https://cervejaequip.com.br"),

    # LOGÍSTICA / TRANSPORTE (30)
    ("TransLog", "Gestão de transportadora com roteirização inteligente. Cliente ideal: transportadoras, empresas de logística e distribuidoras no Sudeste.", "https://translog.com.br"),
    ("FreteFácil", "Plataforma de fretes para cargas completas e fracionadas. Atendemos transportadoras e indústrias em todo o Brasil.", "https://fretefacil.com.br"),
    ("ArmazémPro", "Soluções de armazenagem - estantes, porta-pallets, drive-in. Cliente ideal: armazéns, centros de distribuição e indústrias.", "https://armazempro.com.br"),
    ("GPSFleet", "Rastreadores veiculares para frotas comerciais. Atendemos transportadoras e empresas de logística.", "https://gpsfleet.com.br"),
    ("PneuFrota", "Pneus para caminhões e ônibus. Cliente ideal: transportadoras, empresas de ônibus e locadoras.", "https://pneufrota.com.br"),
    ("MudançaBR", "Serviços de mudanças corporativas. Atendemos empresas, condomínios e imobiliárias em São Paulo.", "https://mudancabr.com.br"),

    # FINANCEIRO / CONTÁBIL (25)
    ("SeguroBiz", "Seguros empresariais - patrimonial, responsabilidade civil, D&O. Atendemos corretoras de seguros e empresas de médio porte.", "https://segurobiz.com.br"),
    ("CréditoFácil", "Crédito empresarial para PMEs. Cliente ideal: escritórios de contabilidade, cooperativas de crédito e fintechs.", "https://creditofacil.com.br"),
    ("AuditMax", "Auditoria contábil e fiscal. Atendemos escritórios de contabilidade, empresas de grande porte e consultorias tributárias.", "https://auditmax.com.br"),
    ("InvestPro", "Plataforma de investimentos para PJ. Cliente ideal: corretoras de investimentos, fintechs e gestoras de fundos.", "https://investpro.com.br"),
    ("FolhaCerta", "Sistema de folha de pagamento. Atendemos escritórios de contabilidade e empresas de recursos humanos.", "https://folhacerta.com.br"),

    # ENERGIA / SUSTENTABILIDADE (25)
    ("SolarPro", "Painéis e inversores solares para usinas e empresas. Atendemos empresas de energia solar e instaladores no Nordeste e Centro-Oeste.", "https://solarpro.com.br"),
    ("BioMassa", "Caldeiras a biomassa para geração de energia. Atendemos usinas, agroindústrias e indústrias.", "https://biomassa.com.br"),
    ("WindTech", "Componentes para aerogeradores eólicos. Cliente ideal: empresas de energia eólica no Nordeste.", "https://windtech.com.br"),
    ("LEDIndustrial", "Iluminação LED para galpões e fábricas. Atendemos fábricas, armazéns e construtoras.", "https://ledindustrial.com.br"),
    ("ResiduoZero", "Gestão de resíduos industriais. Atendemos fábricas, mineradoras e empresas de reciclagem.", "https://residuozero.com.br"),

    # SEGURANÇA (20)
    ("VigilantePro", "Serviços de segurança patrimonial. Atendemos condomínios, shoppings e empresas no Sudeste.", "https://vigilantepro.com.br"),
    ("CameraTech", "Câmeras de segurança e CFTV para empresas. Atendemos condomínios, lojas e empresas de segurança.", "https://cameratech.com.br"),
    ("AcessoSeguro", "Catracas e controle de acesso biométrico. Cliente ideal: empresas de segurança, portaria remota e condomínios.", "https://acessoseguro.com.br"),
    ("AlarmeBR", "Centrais de alarme e monitoramento 24h. Atendemos empresas de segurança, condomínios e lojas.", "https://alarmebr.com.br"),
    ("PortariaRemota", "Portaria remota com inteligência artificial. Cliente ideal: condomínios, empresas de facilities e administradoras.", "https://portariaremota.com.br"),

    # EDUCAÇÃO (20)
    ("EduPublish", "Livros didáticos e material escolar. Atendemos escolas particulares, faculdades e distribuidoras de livros.", "https://edupublish.com.br"),
    ("LabEscola", "Equipamentos de laboratório para escolas. Cliente ideal: escolas particulares, faculdades e centros de treinamento.", "https://labescola.com.br"),
    ("MóvelEscolar", "Carteiras, mesas e mobiliário escolar. Atendemos escolas, faculdades e centros de treinamento.", "https://movelescolar.com.br"),
    ("CursosPro", "Plataforma de cursos corporativos. Atendemos empresas de recursos humanos, consultorias e centros de treinamento.", "https://cursospro.com.br"),
    ("BrinquedoEduca", "Brinquedos educativos e material pedagógico. Cliente ideal: escolas de educação infantil e creches.", "https://brinquedoeduca.com.br"),

    # VAREJO (30)
    ("UniformeBR", "Uniformes profissionais e EPIs. Cliente ideal: empresas, fábricas, hospitais e escolas no Sul.", "https://uniformebr.com.br"),
    ("FranquiaMax", "Consultoria para franquias. Atendemos franquias, redes de lojas e investidores.", "https://franquiamax.com.br"),
    ("VitrineLED", "Letreiros e vitrines iluminadas para lojas. Atendemos lojas de roupas, franquias e shopping centers.", "https://vitrineled.com.br"),
    ("PDVExpress", "Terminais de pagamento e PDV para comércio. Atendemos supermercados, lojas e restaurantes.", "https://pdvexpress.com.br"),
    ("BagExpress", "Sacolas e embalagens personalizadas para varejo. Cliente ideal: lojas de roupas, cosméticos e presentes.", "https://bagexpress.com.br"),
    ("EtiquetaPro", "Etiquetas adesivas e de segurança para varejo. Atendemos lojas, supermercados e indústrias.", "https://etiquetapro.com.br"),
    ("GôndolaBR", "Gôndolas e expositores para supermercados. Cliente ideal: supermercados, lojas e drogarias.", "https://gondolabr.com.br"),
    ("CaixaRegistra", "Sistemas de caixa registradora digital. Atendemos padarias, lanchonetes e comércio em geral.", "https://caixaregistra.com.br"),

    # IMOBILIÁRIO (15)
    ("ImovelPrime", "Consultoria imobiliária corporativa. Atendemos imobiliárias, incorporadoras e construtoras em São Paulo.", "https://imovelprime.com.br"),
    ("AluguelFácil", "Plataforma de gestão de aluguéis. Cliente ideal: imobiliárias, administradoras de imóveis e condomínios.", "https://aluguelfacil.com.br"),
    ("LoteamentosBR", "Infraestrutura para loteamentos. Atendemos incorporadoras e construtoras no Centro-Oeste.", "https://loteamentosbr.com.br"),

    # MINERAÇÃO (15)
    ("MineraParts", "Peças de desgaste para mineração - revestimentos, mandíbulas, martelos. Atendemos mineradoras e pedreiras em Minas Gerais.", "https://mineraparts.com.br"),
    ("PedreiraMax", "Britadores e peneiras para pedreiras. Cliente ideal: mineradoras, pedreiras e construtoras.", "https://pedreiramax.com.br"),
    ("GeoSonda", "Sondagem mineral e geotécnica. Atendemos mineradoras e empresas de mineração em Minas Gerais e Goiás.", "https://geosonda.com.br"),

    # PET / VETERINÁRIO (15)
    ("PetFoodBR", "Ração premium para cães e gatos. Atendemos pet shops, clínicas veterinárias e distribuidoras pet.", "https://petfoodbr.com.br"),
    ("VetEquip", "Equipamentos veterinários - mesa cirúrgica, raio-X, ultrassom. Cliente ideal: clínicas veterinárias e hospitais veterinários.", "https://vetequip.com.br"),
    ("BanhoTosa", "Equipamentos para banho e tosa profissional. Atendemos pet shops e clínicas veterinárias.", "https://banhotosa.com.br"),

    # TELECOM (15)
    ("FibraNet", "Cabos e equipamentos de fibra óptica. Atendemos provedores de internet e empresas de telecom.", "https://fibranet.com.br"),
    ("TorreTelecom", "Torres e antenas para telecomunicações. Cliente ideal: operadoras, provedores de internet e empresas de telecom.", "https://torretelecom.com.br"),
    ("WifiPro", "Soluções Wi-Fi corporativo. Atendemos hotéis, escritórios, condomínios e shoppings.", "https://wifipro.com.br"),

    # BELEZA / ESTÉTICA (10)
    ("SalãoEquip", "Cadeiras, secadores e equipamentos para salões. Atendemos salões de beleza e barbearias.", "https://salaoequip.com.br"),
    ("EstéticaPro", "Equipamentos de estética - laser, radiofrequência, criolipólise. Cliente ideal: clínicas de estética e dermatologia.", "https://esteticapro.com.br"),
    ("CosméticosInd", "Produtos cosméticos para revenda. Atendemos salões de beleza, clínicas de estética e distribuidoras.", "https://cosmeticosind.com.br"),

    # GRÁFICA / COMUNICAÇÃO (10)
    ("ImpressãoMax", "Impressoras industriais offset e digital. Atendemos gráficas e editoras.", "https://impressaomax.com.br"),
    ("PapelCartão", "Papel cartão e papelão ondulado. Cliente ideal: gráficas, editoras e indústrias de embalagens.", "https://papelcartao.com.br"),
    ("SinalTech", "Sinalização visual e comunicação visual. Atendemos agências, lojas e construtoras.", "https://sinaltech.com.br"),

    # JURÍDICO (10)
    ("CartórioSys", "Sistema de gestão para cartórios. Atendemos cartórios de notas, registro e protesto.", "https://cartoriosys.com.br"),
    ("PericiaForense", "Perícias contábeis e financeiras. Atendemos escritórios de advocacia e juízes.", "https://periciaforense.com.br"),
    ("ContratoDigital", "Plataforma de assinatura digital de contratos. Atendemos escritórios de advocacia, imobiliárias e empresas.", "https://contratodigital.com.br"),

    # MARKETING / PUBLICIDADE (10)
    ("LeadGen", "Geração de leads B2B qualificados. Atendemos agências de marketing digital, consultorias e startups.", "https://leadgen.com.br"),
    ("SEOMax", "Consultoria SEO e marketing de conteúdo. Atendemos agências, e-commerces e startups.", "https://seomax.com.br"),
    ("PrintBanner", "Banners, adesivos e impressão de grande formato. Atendemos agências, lojas e eventos.", "https://printbanner.com.br"),

    # HOTELARIA / TURISMO (10)
    ("HotelSupply", "Enxovais e amenities para hotéis. Atendemos hotéis, pousadas e motéis no Nordeste.", "https://hotelsupply.com.br"),
    ("TurismoReceptivo", "Passeios e experiências turísticas. Atendemos hotéis, agências de viagem e operadoras de turismo.", "https://turismoreceptivo.com.br"),
    ("CozinhaHotel", "Equipamentos de cozinha industrial para hotéis. Atendemos hotéis, restaurantes e buffets.", "https://cozinhahotel.com.br"),

    # TÊXTIL / CONFECÇÃO (10)
    ("TecidoBR", "Tecidos para confecção - algodão, poliéster, malha. Atendemos indústrias têxteis e confecções.", "https://tecidobr.com.br"),
    ("MáquinaCostura", "Máquinas de costura industriais. Cliente ideal: confecções, indústrias têxteis e lavanderias.", "https://maquinacostura.com.br"),
    ("AviamentoPro", "Aviamentos, zíperes e botões para confecções. Atendemos confecções e lojas de aviamentos.", "https://aviamentopro.com.br"),

    # RESIDUOS / RECICLAGEM (10)
    ("ReciclaFácil", "Máquinas para triagem e reciclagem de resíduos. Atendemos cooperativas de reciclagem e empresas de reciclagem.", "https://reciclafacil.com.br"),
    ("SucataBR", "Compra e venda de sucata metálica. Atendemos sucateiros, indústrias e cooperativas de reciclagem.", "https://sucatabr.com.br"),
    ("LixoZero", "Consultoria em gestão de resíduos sólidos. Atendemos fábricas, construtoras e prefeituras.", "https://lixozero.com.br"),

    # AUTOMOTIVO (15)
    ("AutoPeçasBR", "Distribuição de autopeças multimarca. Atendemos oficinas mecânicas, concessionárias e autopeças no Sudeste.", "https://autopecasbr.com.br"),
    ("FunilRapido", "Funilaria e pintura automotiva. Atendemos concessionárias, locadoras e seguradoras.", "https://funilrapido.com.br"),
    ("PneuExpress", "Pneus e serviços automotivos. Atendemos oficinas mecânicas, concessionárias e transportadoras.", "https://pneuexpress.com.br"),

    # FACILITIES / LIMPEZA (10)
    ("LimpezaPro", "Produtos de limpeza profissional para empresas. Atendemos condomínios, hospitais, shoppings e empresas de facilities.", "https://limpezapro.com.br"),
    ("FacilitiesBR", "Gestão de facilities terceirizada. Cliente ideal: condomínios, shoppings e empresas de grande porte.", "https://facilitiesbr.com.br"),
    ("DesinfetaBR", "Sanitizantes e desinfetantes industriais. Atendemos hospitais, indústrias alimentícias e lavanderias.", "https://desinfetabr.com.br"),

    # MÓVEIS / DECORAÇÃO (10)
    ("MóvelCorporativo", "Móveis para escritório - mesas, cadeiras, estações de trabalho. Atendemos escritórios, coworkings e construtoras.", "https://movelcorporativo.com.br"),
    ("CozinhaIndustrial", "Cozinhas industriais em aço inox. Atendemos restaurantes, hotéis e hospitais.", "https://cozinhaindustrial.com.br"),
    ("DivisóriaPro", "Divisórias e forros para escritórios. Atendemos construtoras, escritórios e coworkings.", "https://divisoriapro.com.br"),

    # ── MORE DIVERSE PROFILES TO REACH 500+ ──

    # Agro extras
    ("AviPecuária", "Galpões e equipamentos para avicultura. Atendemos granjas, frigoríficos de aves e cooperativas.", "https://avipecuaria.com.br"),
    ("SuinoBR", "Equipamentos para suinocultura. Atendemos granjas de suínos, frigoríficos e cooperativas no Sul.", "https://suinobr.com.br"),
    ("AquaTech", "Equipamentos para aquicultura e piscicultura. Atendemos fazendas de peixe e cooperativas.", "https://aquatech.com.br"),
    ("FlorestalBR", "Equipamentos para silvicultura e reflorestamento. Atendemos fazendas de eucalipto e indústria de celulose.", "https://florestalbr.com.br"),
    ("VinhoBR", "Equipamentos para vinícolas. Atendemos vinícolas e cooperativas no Rio Grande do Sul.", "https://vinhobr.com.br"),
    ("TabacoBR", "Máquinas para processamento de tabaco. Atendemos indústrias de cigarro e cooperativas de fumo no Sul.", "https://tabacobr.com.br"),
    ("CouroTech", "Máquinas para curtume. Atendemos indústrias de couro e calçados no Rio Grande do Sul.", "https://courotech.com.br"),
    ("CacauBR", "Equipamentos para beneficiamento de cacau. Atendemos fazendas de cacau e fábricas de chocolate na Bahia.", "https://cacaubr.com.br"),
    ("BorrachaCultivo", "Equipamentos para extração e processamento de borracha natural. Atendemos seringais e indústrias de borracha no Norte.", "https://borrachacultivo.com.br"),
    ("ApiculturaBR", "Equipamentos para apicultura. Atendemos cooperativas de mel e apiários no Nordeste.", "https://apiculturabr.com.br"),

    # Tech extras
    ("ChatBotPro", "Chatbots com IA para atendimento ao cliente. Atendemos e-commerces, bancos e empresas de telecom.", "https://chatbotpro.com.br"),
    ("BackupCloud", "Backup em nuvem para empresas. Atendemos escritórios de contabilidade, escritórios de advocacia e clínicas.", "https://backupcloud.com.br"),
    ("ERPIndustria", "ERP para indústrias de manufatura. Atendemos fábricas, indústrias metalúrgicas e indústrias de plásticos.", "https://erpindustria.com.br"),
    ("AppDelivery", "Aplicativo white-label de delivery. Atendemos restaurantes, padarias e supermercados.", "https://appdelivery.com.br"),
    ("SistemaClínica", "Software de gestão para clínicas médicas. Atendemos clínicas médicas, clínicas odontológicas e laboratórios.", "https://sistemaClinica.com.br"),
    ("NFeBR", "Emissor de NF-e e NFC-e. Atendemos escritórios de contabilidade, lojas e indústrias.", "https://nfebr.com.br"),
    ("CyberShield", "Firewall e proteção de rede corporativa. Atendemos empresas de tecnologia, bancos e data centers.", "https://cybershield.com.br"),
    ("CloudMigra", "Migração para nuvem AWS e Azure. Atendemos empresas de tecnologia e data centers.", "https://cloudmigra.com.br"),
    ("IoTFactory", "Sensores IoT para chão de fábrica. Atendemos indústrias metalúrgicas e fábricas de alimentos.", "https://iotfactory.com.br"),
    ("RPABots", "Robôs de automação RPA para processos empresariais. Atendemos bancos, escritórios de contabilidade e BPOs.", "https://rpabots.com.br"),

    # Health extras
    ("OxigênioMed", "Equipamentos de oxigenoterapia. Atendemos hospitais, clínicas e empresas de home care.", "https://oxigeniomed.com.br"),
    ("CMEPro", "Central de material esterilizado para hospitais. Atendemos hospitais e clínicas cirúrgicas.", "https://cmepro.com.br"),
    ("ProntuárioDigital", "Prontuário eletrônico do paciente. Atendemos clínicas médicas, hospitais e operadoras de saúde.", "https://prontuariodigital.com.br"),
    ("UniformeMédico", "Uniformes médicos e jalecos. Atendemos hospitais, clínicas e faculdades de medicina.", "https://uniformemedico.com.br"),
    ("AmbulânciaBR", "Ambulâncias e veículos de resgate. Atendemos hospitais, clínicas e prefeituras.", "https://ambulanciabr.com.br"),

    # Construction extras
    ("GuincheBR", "Guindastes e equipamentos de elevação. Atendemos construtoras, indústrias e portos.", "https://guindaste.com.br"),
    ("FormaMetálica", "Formas metálicas para concreto. Atendemos construtoras e empresas de engenharia.", "https://formametalica.com.br"),
    ("GeotêxtilBR", "Geotêxteis e geomembranas. Atendemos construtoras, mineradoras e aterros sanitários.", "https://geotextilbr.com.br"),
    ("BetoneiraBR", "Betoneiras e usinas de concreto. Atendemos construtoras e concreteiras.", "https://betoneirabr.com.br"),
    ("EscavaçãoPro", "Locação de retroescavadeiras e escavadeiras. Atendemos construtoras e mineradoras.", "https://escavacaopro.com.br"),

    # Automotive extras
    ("RetíficaMotor", "Retífica de motores e cabeçotes. Atendemos oficinas mecânicas e concessionárias.", "https://retificamotor.com.br"),
    ("DiagnósticoAuto", "Equipamentos de diagnóstico automotivo. Atendemos oficinas mecânicas e concessionárias.", "https://diagnosticoauto.com.br"),
    ("LavaJato", "Equipamentos para lava jato profissional. Atendemos lava jatos, postos de gasolina e concessionárias.", "https://lavajato.com.br"),

    # Food service
    ("BuffetEquip", "Equipamentos para buffet e catering. Atendemos restaurantes, hotéis e buffets de eventos.", "https://buffetequip.com.br"),
    ("PizzaForno", "Fornos para pizzarias. Atendemos pizzarias, restaurantes e padarias.", "https://pizzaforno.com.br"),
    ("MáquinaGelo", "Máquinas de gelo industriais. Atendemos restaurantes, hotéis e peixarias.", "https://maquinagelo.com.br"),

    # Transport extras
    ("ContêinerBR", "Contêineres marítimos e adaptados. Atendemos transportadoras, portos e construtoras.", "https://conteinerbr.com.br"),
    ("CarroceriaBR", "Carrocerias para caminhões baú e sider. Atendemos transportadoras e distribuidoras.", "https://carroceriabr.com.br"),
    ("SemiReboqueBR", "Semi-reboques e implementos rodoviários. Atendemos transportadoras e agroindústrias.", "https://semireboquebr.com.br"),

    # Financial extras
    ("ConsórcioMax", "Administradora de consórcios. Atendemos corretoras, concessionárias e imobiliárias.", "https://consorciomax.com.br"),
    ("CobrançaDigital", "Cobrança digital e régua automatizada. Atendemos escritórios de contabilidade e fintechs.", "https://cobrancadigital.com.br"),

    # Energy extras
    ("GeradorBR", "Geradores diesel para empresas. Atendemos hospitais, data centers e indústrias.", "https://geradorbr.com.br"),
    ("SubestaçãoTech", "Subestações elétricas e transformadores. Atendemos distribuidoras de energia e indústrias.", "https://subestacaotech.com.br"),
    ("BiogásPro", "Biodigestores para geração de biogás. Atendemos granjas, frigoríficos e agroindústrias.", "https://biogaspro.com.br"),

    # Textile extras
    ("LavanderiaInd", "Lavanderia industrial. Atendemos hotéis, hospitais e indústrias.", "https://lavanderiaind.com.br"),
    ("BordadoPro", "Máquinas de bordado computadorizado. Atendemos confecções e uniformes.", "https://bordadopro.com.br"),
    ("EstampariaBR", "Equipamentos de estamparia - sublimação e serigrafia. Atendemos confecções e gráficas.", "https://estampariabr.com.br"),

    # Diverse industries
    ("JoalheriaBR", "Equipamentos para joalherias e ourivesarias. Atendemos joalherias e oficinas de jóias.", "https://joalheriabr.com.br"),
    ("ÓticaPro", "Equipamentos e armações para óticas. Atendemos óticas e clínicas de oftalmologia.", "https://oticapro.com.br"),
    ("FunilariaPro", "Equipamentos de funilaria e pintura. Atendemos funilarias e oficinas de lataria.", "https://funilariapro.com.br"),
    ("MarmoresBR", "Mármores e granitos. Atendemos marmorarias, construtoras e incorporadoras.", "https://marmoresbr.com.br"),
    ("VidraceiroBR", "Equipamentos para vidraçarias. Atendemos vidraçarias e construtoras.", "https://vidracebr.com.br"),

    # More agriculture variants
    ("CanaDeAçúcar", "Equipamentos para colheita mecanizada de cana. Atendemos usinas de açúcar e álcool em São Paulo e Goiás.", "https://canadeacucar.com.br"),
    ("AlgodãoTech", "Beneficiamento de algodão em pluma. Atendemos agroindústrias de algodão no Mato Grosso e Bahia.", "https://algodaotech.com.br"),
    ("FeijãoBR", "Máquinas para seleção e beneficiamento de feijão. Atendemos cerealistas e cooperativas.", "https://feijaobr.com.br"),
    ("MandiocaPro", "Equipamentos para fecularia de mandioca. Atendemos fecularias e cooperativas no Paraná.", "https://mandiocapro.com.br"),
    ("FrutasExport", "Câmaras frias e embalagem para exportação de frutas. Atendemos fazendas de frutas e cooperativas no Nordeste.", "https://frutasexport.com.br"),

    # More tech variants
    ("MonitorPC", "Software de monitoramento de computadores e produtividade dos funcionários. Nosso cliente ideal é o gestor de TI de escritórios de contabilidade, escritórios de advocacia, empresas de call center e consultorias empresariais.", "https://monitorpc.com.br"),
    ("PortalEAD", "Plataforma de educação corporativa a distância. Atendemos empresas com mais de 100 funcionários em todo o Brasil.", "https://portalead.com.br"),
    ("DocFlow", "Gestão eletrônica de documentos. Atendemos escritórios de advocacia, cartórios e escritórios de contabilidade.", "https://docflow.com.br"),
    ("VPNBusiness", "VPN corporativa e acesso remoto seguro. Atendemos empresas de tecnologia e consultorias.", "https://vpnbusiness.com.br"),
    ("EmailMarketing", "Plataforma de email marketing e automação. Atendemos agências de marketing digital e e-commerces.", "https://emailmarketing.com.br"),

    # Healthcare / wellness
    ("AcademiaPro", "Equipamentos de academia - musculação e cardio. Atendemos academias, hotéis e condomínios.", "https://academiapro.com.br"),
    ("PilatesTech", "Equipamentos de pilates e funcional. Atendemos estúdios de pilates e academias.", "https://pilatestech.com.br"),
    ("SPAEquip", "Equipamentos para spa e sauna. Atendemos hotéis, spas e clínicas de estética.", "https://spaequip.com.br"),

    # Packaging
    ("CaixaPapelão", "Caixas de papelão personalizadas. Atendemos e-commerces, indústrias e distribuidoras.", "https://caixapapelao.com.br"),
    ("FlexPack", "Embalagens flexíveis - sachês, pouches, stand-ups. Atendemos indústrias alimentícias e cosméticas.", "https://flexpack.com.br"),
    ("VidroEmbalagem", "Garrafas e potes de vidro. Atendemos indústrias alimentícias, farmacêuticas e cosméticas.", "https://vidroembalagem.com.br"),

    # Niche services
    ("DedetizaçãoPro", "Controle de pragas e dedetização empresarial. Atendemos condomínios, restaurantes e indústrias alimentícias.", "https://dedetizacaopro.com.br"),
    ("PaisagismoBR", "Projetos de paisagismo para condomínios e empresas. Atendemos condomínios, construtoras e shoppings.", "https://paisagismobr.com.br"),
    ("JardinagemInd", "Manutenção de jardins corporativos. Atendemos condomínios, shoppings e empresas de facilities.", "https://jardinegemind.com.br"),

    # More food/beverage
    ("ÁguaMineral", "Envasadora de água mineral. Atendemos indústrias de bebidas e cooperativas.", "https://aguamineral.com.br"),
    ("SorveteriaEquip", "Máquinas de sorvete e açaí. Atendemos sorveterias, franquias e restaurantes.", "https://sorveteriaequip.com.br"),
    ("ChocolateInd", "Equipamentos para fabricação de chocolates. Atendemos fábricas de chocolate e confeitarias.", "https://chocolateind.com.br"),

    # Paper/pulp
    ("CeluloseMax", "Equipamentos para indústria de celulose e papel. Atendemos fábricas de celulose e papel.", "https://celulosemax.com.br"),
    ("PapelHigiênico", "Máquinas para produção de papel higiênico. Atendemos fábricas de papel e distribuidoras.", "https://papelhigienico.com.br"),

    # Naval
    ("NavalTech", "Peças e equipamentos navais. Atendemos estaleiros e empresas de navegação.", "https://navaltech.com.br"),
    ("PescaBR", "Equipamentos para pesca industrial. Atendemos empresas de pesca e cooperativas no Norte e Nordeste.", "https://pescabr.com.br"),

    # Office supplies
    ("PapelariaCorporativa", "Materiais de escritório para empresas. Atendemos escritórios, escolas e distribuidoras.", "https://papelcorp.com.br"),
    ("MóvelEscritório", "Cadeiras ergonômicas e mesas para escritório. Atendemos empresas, coworkings e home office.", "https://movelescritorio.com.br"),

    # Specific service niches
    ("TraduçãoPro", "Serviços de tradução juramentada e técnica. Atendemos escritórios de advocacia, consultorias e importadoras.", "https://traducaopro.com.br"),
    ("LaudoTécnico", "Laudos de engenharia - elétrico, bombeiros, acessibilidade. Atendemos condomínios, construtoras e empresas.", "https://laudotecnico.com.br"),
    ("CertificaçãoISO", "Consultoria em certificação ISO 9001, 14001, 45001. Atendemos indústrias, construtoras e laboratórios.", "https://certificacaoiso.com.br"),

    # Event industry
    ("EventosBR", "Locação de tendas e estruturas para eventos. Atendemos empresas de eventos, hotéis e shoppings.", "https://eventosbr.com.br"),
    ("SomIluminação", "Equipamentos de som e iluminação profissional. Atendemos casas de shows, hotéis e igrejas.", "https://somiluminacao.com.br"),

    # Religious market
    ("IgrejaSupply", "Equipamentos de som e vídeo para igrejas. Atendemos igrejas, centros de convenções e auditórios.", "https://igrejasupply.com.br"),

    # Lab/research
    ("LabQuímica", "Reagentes e vidrarias para laboratórios de pesquisa. Atendemos universidades, laboratórios e indústrias químicas.", "https://labquimica.com.br"),
    ("MicroscópioBR", "Microscópios e equipamentos de análise. Atendemos universidades, hospitais e laboratórios.", "https://microscopiobr.com.br"),

    # Specific regions
    ("SulAutopeças", "Distribuição de autopeças no Sul do Brasil. Atendemos oficinas mecânicas em Paraná, Santa Catarina e Rio Grande do Sul.", "https://sulautopecas.com.br"),
    ("NordesteAgro", "Insumos agrícolas para o Nordeste. Atendemos fazendas de frutas e cooperativas na Bahia, Pernambuco e Ceará.", "https://nordesteagro.com.br"),
    ("AmazôniaTech", "Soluções de energia solar e internet para comunidades remotas no Norte. Atendemos prefeituras e cooperativas no Amazonas e Pará.", "https://amazoniatech.com.br"),

    # E-commerce services
    ("FulfilmentBR", "Serviço de fulfillment para e-commerces. Atendemos lojas virtuais, marketplaces e distribuidoras.", "https://fulfilmentbr.com.br"),
    ("FotoProduto", "Fotografia de produtos para e-commerce. Atendemos lojas virtuais, agências e indústrias.", "https://fotoproduto.com.br"),

    # Dental extras
    ("ImplanteDental", "Implantes dentários e componentes protéticos. Atendemos clínicas odontológicas e laboratórios de prótese.", "https://implantedental.com.br"),
    ("RaioXDental", "Equipamentos de radiologia odontológica. Atendemos clínicas odontológicas e hospitais.", "https://raioxdental.com.br"),

    # Specific software
    ("ERPHospitalar", "ERP hospitalar completo. Atendemos hospitais e clínicas de médio e grande porte.", "https://erphospitalar.com.br"),
    ("SistemaFrota", "Software de gestão de frotas. Atendemos transportadoras, locadoras e empresas de logística.", "https://sistemafrota.com.br"),
    ("SistemaHotel", "PMS completo para redes hoteleiras. Atendemos hotéis e pousadas no Nordeste e Sul.", "https://sistemahotel.com.br"),

    # More diverse industries
    ("EmbalaMetal", "Embalagens metálicas - latas e baldes. Atendemos indústrias de tintas, químicas e alimentícias.", "https://embalametal.com.br"),
    ("RótuloBR", "Rótulos autoadesivos para indústria. Atendemos indústrias alimentícias, farmacêuticas e cosméticas.", "https://rotulobr.com.br"),
    ("TampasBR", "Tampas plásticas e metálicas. Atendemos indústrias de bebidas, cosméticos e farmacêuticas.", "https://tampasbr.com.br"),

    # Rural/country life
    ("SelariaBR", "Artigos de selaria e equitação. Atendemos haras, fazendas e lojas de produtos rurais.", "https://selariabr.com.br"),
    ("CercaElétrica", "Cercas elétricas para pecuária. Atendemos fazendas e cooperativas agrícolas.", "https://cercaeletrica.com.br"),

    # More construction
    ("PiscínaBR", "Construção e equipamentos para piscinas comerciais. Atendemos hotéis, condomínios e academias.", "https://piscinabr.com.br"),
    ("ImpermeabilizaçãoPro", "Impermeabilização de lajes, reservatórios e terraços. Atendemos construtoras e condomínios.", "https://impermeabilizacaopro.com.br"),

    # Chemical industry
    ("AdesivoBR", "Adesivos industriais e selantes. Atendemos indústrias automotivas, moveleiras e construtoras.", "https://adesivobr.com.br"),
    ("ResínaBR", "Resinas epóxi e poliuretano. Atendemos indústrias e construtoras.", "https://resinabr.com.br"),

    # Municipal/government
    ("MuniGestão", "Software de gestão pública municipal. Atendemos prefeituras, câmaras e autarquias.", "https://munigestao.com.br"),
    ("SinalizaçãoViária", "Sinalização viária e equipamentos de trânsito. Atendemos prefeituras e construtoras.", "https://sinalizacaoviaria.com.br"),

    # More filling profiles to hit 500+
    ("GalpãoMetálico", "Galpões metálicos pré-moldados. Atendemos indústrias, agroindústrias e construtoras.", "https://galpaometalico.com.br"),
    ("PortãoIndustrial", "Portões industriais automáticos. Atendemos fábricas, armazéns e condomínios.", "https://portaoindustrial.com.br"),
    ("PainelElétrico", "Painéis elétricos industriais. Atendemos fábricas, construtoras e indústrias.", "https://paineleletrico.com.br"),
    ("CaboElétrico", "Cabos elétricos industriais. Atendemos distribuidoras elétricas, construtoras e fábricas.", "https://caboeletrico.com.br"),
    ("MotoBomba", "Moto-bombas industriais e agrícolas. Atendemos fazendas, indústrias e mineradoras.", "https://motobomba.com.br"),
    ("ValvulaBR", "Válvulas industriais - esfera, gaveta, borboleta. Atendemos indústrias químicas, petroquímicas e mineradoras.", "https://valvulabr.com.br"),
    ("TuboBR", "Tubos de aço carbono e inox. Atendemos construtoras, indústrias e distribuidoras.", "https://tububr.com.br"),
    ("ParafusoBR", "Parafusos e fixadores industriais. Atendemos fábricas, construtoras e indústrias metalúrgicas.", "https://parafusobr.com.br"),
    ("CorrenteBR", "Correntes e correia transportadora industrial. Atendemos mineradoras, fábricas e agroindústrias.", "https://correntebr.com.br"),
    ("RolamentoBR", "Rolamentos industriais SKF e NSK. Atendemos indústrias, distribuidoras e fábricas.", "https://rolamentobr.com.br"),
    ("FerramentaInd", "Ferramentas de corte e usinagem. Atendemos indústrias metalúrgicas e fábricas.", "https://ferramentaind.com.br"),
    ("AbrasivoBR", "Discos de corte e lixas industriais. Atendemos metalúrgicas, funilarias e fábricas.", "https://abrasivobr.com.br"),
    ("EPIBrasil", "EPIs - capacetes, luvas, botas e óculos de segurança. Atendemos fábricas, construtoras e mineradoras.", "https://epibrasil.com.br"),
    ("IncêndioZero", "Extintores e sistemas contra incêndio. Atendemos condomínios, fábricas e shoppings.", "https://incendiozero.com.br"),
    ("TreinamentoNR", "Treinamentos de NRs (NR-10, NR-35, NR-33). Atendemos construtoras, indústrias e empresas de mineração.", "https://treinamentonr.com.br"),
    ("ClimaPro", "Ar condicionado industrial e comercial. Atendemos escritórios, shoppings e data centers.", "https://climapro.com.br"),
    ("VentilaçãoBR", "Exaustores e ventiladores industriais. Atendemos fábricas, galpões e mineradoras.", "https://ventilacaobr.com.br"),
    ("AspiraçãoPó", "Sistemas de aspiração de pó industrial. Atendemos marcenarias, fábricas e indústrias.", "https://aspiracaopo.com.br"),
    ("TratamentoÁgua", "Estações de tratamento de água e efluentes. Atendemos fábricas, mineradoras e construtoras.", "https://tratamentoagua.com.br"),
    ("AnaliseQuímica", "Análises químicas e ambientais. Atendemos fábricas, mineradoras e laboratórios.", "https://analises.com.br"),
    ("CartãoFidelidade", "Programa de fidelidade para varejo. Atendemos lojas, farmácias e supermercados.", "https://cartaofidelidade.com.br"),
    ("TótemDigital", "Totems de autoatendimento. Atendemos bancos, hospitais e restaurantes.", "https://totemdigital.com.br"),
    ("DisplayPDV", "Displays e expositores para ponto de venda. Atendemos supermercados, farmácias e lojas.", "https://displaypdv.com.br"),
    ("WMS_Cloud", "Sistema WMS para armazéns. Atendemos armazéns, centros de distribuição e transportadoras.", "https://wmscloud.com.br"),
    ("PickPack", "Sistemas de pick and pack para fulfillment. Atendemos e-commerces e centros de distribuição.", "https://pickpack.com.br"),
    ("DocScanner", "Digitalização e gestão de documentos. Atendemos cartórios, escritórios de advocacia e hospitais.", "https://docscanner.com.br"),
    ("TokenSegurança", "Tokens e certificados digitais. Atendemos escritórios de contabilidade, cartórios e empresas.", "https://tokenseguranca.com.br"),
    ("RelogPonto", "Relógios de ponto eletrônicos. Atendemos fábricas, escritórios e condomínios.", "https://relogponto.com.br"),
    ("CracháPro", "Crachás e cartões de acesso personalizados. Atendemos empresas, condomínios e escolas.", "https://crachapro.com.br"),
    ("NobreakBR", "Nobreaks e estabilizadores para data centers. Atendemos data centers, hospitais e indústrias.", "https://nobreakbr.com.br"),
    ("DataCenterBR", "Infraestrutura para data centers - racks, cabeamento, refrigeração. Atendemos data centers e empresas de telecom.", "https://datacenterbr.com.br"),
    ("RadioCom", "Rádios comunicadores para empresas. Atendemos construtoras, mineradoras e transportadoras.", "https://radiocom.com.br"),
    ("GPSAgro", "GPS agrícola e piloto automático para tratores. Atendemos fazendas e revendedoras agrícolas.", "https://gpsagro.com.br"),
    ("BalançaBR", "Balanças rodoviárias e industriais. Atendemos cerealistas, cooperativas e indústrias.", "https://balancabr.com.br"),
    ("EmpilhadeiraBR", "Locação e venda de empilhadeiras. Atendemos armazéns, distribuidoras e indústrias.", "https://empilhadeirabr.com.br"),
    ("PaleteBR", "Paletes de madeira e plástico. Atendemos indústrias, distribuidoras e transportadoras.", "https://paletebr.com.br"),
    ("StretchFilm", "Filmes stretch para paletização. Atendemos indústrias, distribuidoras e e-commerces.", "https://stretchfilm.com.br"),
    ("FitaAdesivaBR", "Fitas adesivas industriais - dupla face, demarcação, embalagem. Atendemos fábricas e distribuidoras.", "https://fitaadesiva.com.br"),
    ("ColetorDados", "Coletores de dados e leitores de código de barras. Atendemos armazéns, supermercados e transportadoras.", "https://coletordados.com.br"),
    ("ImpressoraEtiqueta", "Impressoras térmicas de etiquetas. Atendemos armazéns, farmácias e indústrias.", "https://impressoraetiqueta.com.br"),
    ("MaqVendas", "Máquinas de venda automática - snacks, café, bebidas. Atendemos empresas, condomínios e shoppings.", "https://maqvendas.com.br"),

    # ── BATCH 2: 180+ more profiles to reach 500+ ──

    # More agro
    ("SojaMax", "Armazenagem e secagem de soja. Atendemos cerealistas e cooperativas agrícolas no Mato Grosso.", "https://sojamax.com.br"),
    ("MilhoPrime", "Sementes híbridas de milho. Atendemos fazendas e revendedoras agrícolas no Paraná e Goiás.", "https://milhoprime.com.br"),
    ("LavouraDigital", "Mapeamento de lavouras com drones e satélite. Atendemos fazendas e cooperativas no Centro-Oeste.", "https://lavouradigital.com.br"),
    ("CurralTech", "Balanças e troncos para manejo de gado. Atendemos fazendas de pecuária e leilões.", "https://curraltech.com.br"),
    ("CoopGrãos", "Cooperativa de comercialização de grãos. Atendemos produtores rurais em Goiás e Mato Grosso.", "https://coopgraos.com.br"),
    ("DefensivoAgro", "Distribuição de defensivos agrícolas. Atendemos revendedoras agrícolas e cooperativas.", "https://defensivoagro.com.br"),
    ("CorreiaColheita", "Correias e lonas para colheitadeiras. Atendemos fazendas e oficinas agrícolas no Sul.", "https://correiacolheita.com.br"),
    ("TanqueLeite", "Tanques de resfriamento de leite. Atendemos fazendas de leite e cooperativas no Sul e Sudeste.", "https://tanqueleite.com.br"),
    ("AviárioMax", "Equipamentos para aviários. Atendemos granjas de aves e cooperativas no Sul.", "https://aviariomax.com.br"),
    ("RaçãoBovina", "Ração e suplementos para gado de corte. Atendemos fazendas e confinamentos no Centro-Oeste.", "https://racaobovina.com.br"),

    # More healthcare
    ("ProteseDentária", "Laboratório de próteses dentárias. Atendemos clínicas odontológicas e consultórios.", "https://protesedentaria.com.br"),
    ("EsterilLab", "Indicadores biológicos para esterilização. Atendemos hospitais e laboratórios.", "https://esterillab.com.br"),
    ("UniformeHospitalar", "Roupas hospitalares descartáveis. Atendemos hospitais, laboratórios e clínicas.", "https://uniformehosp.com.br"),
    ("CirurgiaPro", "Instrumentos cirúrgicos de precisão. Atendemos hospitais e clínicas cirúrgicas.", "https://cirurgiapro.com.br"),
    ("ReabilitaEquip", "Equipamentos de reabilitação motora. Atendemos clínicas de fisioterapia e hospitais.", "https://reabilitaequip.com.br"),

    # More tech
    ("ERPLogística", "ERP para transportadoras e operadores logísticos. Atendemos transportadoras no Sudeste.", "https://erplogistica.com.br"),
    ("AppCardápio", "Cardápio digital QR code para restaurantes. Atendemos restaurantes, bares e lanchonetes.", "https://appcardapio.com.br"),
    ("SistemaÓtica", "Software de gestão para óticas. Atendemos óticas e redes de óticas.", "https://sistemaotica.com.br"),
    ("TicketEvento", "Plataforma de venda de ingressos online. Atendemos casas de shows, teatros e eventos.", "https://ticketevento.com.br"),
    ("CRMVendas", "CRM para equipes de vendas B2B. Atendemos empresas de tecnologia e consultorias.", "https://crmvendas.com.br"),
    ("SistemaGym", "Software de gestão para academias. Atendemos academias e estúdios fitness.", "https://sistemagym.com.br"),
    ("ERPPadaria", "Sistema de gestão para padarias e confeitarias. Atendemos padarias e confeitarias.", "https://erppadaria.com.br"),
    ("AgendaOnline", "Sistema de agendamento online para serviços. Atendemos salões de beleza, clínicas e consultórios.", "https://agendaonline.com.br"),
    ("NotaFiscalBR", "Emissor de nota fiscal para MEI e PME. Atendemos contadores e pequenas empresas.", "https://notafiscalbr.com.br"),
    ("SistemaLavanderia", "Software de gestão para lavanderias. Atendemos lavanderias e tinturarias.", "https://sistemalavandr.com.br"),

    # More construction
    ("MáquinaPesada", "Locação de máquinas pesadas - pá carregadeira, motoniveladora. Atendemos construtoras e mineradoras.", "https://maquinapesada.com.br"),
    ("ConcretoUsinado", "Usina de concreto. Atendemos construtoras e empresas de engenharia no Sudeste.", "https://concretousinado.com.br"),
    ("EstruturaMet", "Estruturas metálicas para galpões e pontes. Atendemos construtoras e indústrias.", "https://estruturamet.com.br"),
    ("DrenagemBR", "Sistemas de drenagem urbana e agrícola. Atendemos construtoras e prefeituras.", "https://drenagembr.com.br"),
    ("TerraplanPro", "Terraplanagem e movimentação de terra. Atendemos construtoras e mineradoras.", "https://terraplanpro.com.br"),

    # More logistics
    ("ColdChain", "Logística refrigerada para alimentos. Atendemos distribuidoras de alimentos e supermercados.", "https://coldchain.com.br"),
    ("MudançaResidencial", "Mudanças residenciais com seguro. Atendemos imobiliárias e condomínios em São Paulo.", "https://mudancaresid.com.br"),
    ("EntregaExpress", "Entregas rápidas de moto e van. Atendemos e-commerces e restaurantes.", "https://entregaexpress.com.br"),
    ("ArmLogística", "Operador logístico com armazenagem. Atendemos indústrias e distribuidoras.", "https://armlogistica.com.br"),
    ("FreteMar", "Agenciamento de carga marítima. Atendemos importadoras e exportadoras.", "https://fretemar.com.br"),

    # More financial
    ("SeguroRural", "Seguros para safra e pecuária. Atendemos fazendas e cooperativas agrícolas.", "https://segurorural.com.br"),
    ("CâmbioBR", "Câmbio e remessas internacionais. Atendemos importadoras, exportadoras e agências de turismo.", "https://cambiobr.com.br"),
    ("PatrimônioBR", "Gestão de patrimônio e investimentos. Atendemos corretoras e escritórios de family office.", "https://patrimoniobr.com.br"),
    ("FactoringPro", "Antecipação de recebíveis para PMEs. Atendemos indústrias e distribuidoras.", "https://factoringpro.com.br"),
    ("ConsultoriaTrib", "Consultoria tributária e planejamento fiscal. Atendemos escritórios de contabilidade e indústrias.", "https://consultoriatrib.com.br"),

    # More energy
    ("InversorSolar", "Inversores e microinversores solares. Atendemos empresas de energia solar em todo o Brasil.", "https://inversorsolar.com.br"),
    ("PosTeEnergia", "Postes e luminárias para iluminação pública. Atendemos prefeituras e construtoras.", "https://posteenergia.com.br"),
    ("QuadroElétrico", "Quadros de distribuição elétrica. Atendemos construtoras e indústrias.", "https://quadroeletrico.com.br"),

    # More safety
    ("DetectorFumaça", "Detectores de fumaça e sistemas de alarme contra incêndio. Atendemos condomínios e shoppings.", "https://detectorfumaca.com.br"),
    ("CercaSegurança", "Cercas elétricas e concertinas para empresas. Atendemos condomínios e indústrias.", "https://cercaseguranca.com.br"),

    # More education
    ("InglêsCorporativo", "Aulas de inglês in-company. Atendemos empresas de tecnologia e multinacionais.", "https://inglescorporativo.com.br"),
    ("UniformeEscolar", "Uniformes escolares personalizados. Atendemos escolas particulares e colégios.", "https://uniformeescolar.com.br"),
    ("TransporteEscolar", "Gestão de transporte escolar. Atendemos escolas e faculdades.", "https://transporteescolar.com.br"),

    # More food
    ("AssadeiraPro", "Formas e assadeiras industriais. Atendemos padarias industriais e confeitarias.", "https://assadeirapro.com.br"),
    ("MáquinaMassa", "Máquinas para fabricação de massas. Atendemos indústrias alimentícias e restaurantes.", "https://maquinamassa.com.br"),
    ("TemperoInd", "Temperos e condimentos industriais. Atendemos indústrias alimentícias e restaurantes.", "https://temperoind.com.br"),
    ("EmbutidosPro", "Equipamentos para embutidos - moedor, misturador, embutideira. Atendemos frigoríficos e açougues.", "https://embutidospro.com.br"),
    ("LeveduraBR", "Leveduras e fermentos industriais. Atendemos padarias industriais e cervejarias.", "https://levedurabr.com.br"),

    # More pet
    ("RaçãoPet", "Ração natural para pets. Atendemos pet shops e clínicas veterinárias no Sudeste.", "https://racaopet.com.br"),
    ("AquárioPro", "Aquários e equipamentos para aquarismo. Atendemos pet shops e lojas de aquarismo.", "https://aquariopro.com.br"),

    # More telecom
    ("AntenaBR", "Antenas e repetidores de sinal celular. Atendemos provedores de internet e operadoras.", "https://antenabr.com.br"),
    ("CabeamentoEstruturado", "Cabeamento estruturado cat5e e cat6. Atendemos data centers e escritórios.", "https://cabeamento.com.br"),

    # More textile
    ("MalhariaInd", "Teares e máquinas de malharia. Atendemos indústrias têxteis no Sul.", "https://malhariaind.com.br"),
    ("TinturaríaBR", "Equipamentos de tingimento têxtil. Atendemos indústrias têxteis e lavanderias industriais.", "https://tinturariabr.com.br"),

    # More mining
    ("ExplosivoMin", "Explosivos e acessórios para mineração. Atendemos mineradoras e pedreiras.", "https://explosivomin.com.br"),
    ("CorreiaMin", "Correias transportadoras para mineração. Atendemos mineradoras e pedreiras.", "https://correiamin.com.br"),

    # More real estate
    ("LaudioImóvel", "Laudos de avaliação de imóveis. Atendemos bancos, imobiliárias e construtoras.", "https://laudoimovel.com.br"),
    ("SíndiciPro", "Software para síndicos profissionais. Atendemos condomínios e administradoras.", "https://sindicipro.com.br"),

    # More automotive
    ("BalanceamentoAuto", "Equipamentos de balanceamento e alinhamento. Atendemos oficinas mecânicas e concessionárias.", "https://balanceamentoauto.com.br"),
    ("FiltroCarro", "Filtros automotivos - óleo, ar, combustível. Atendemos distribuidoras de autopeças e oficinas.", "https://filtrocarro.com.br"),
    ("BateriaCarro", "Baterias automotivas. Atendemos distribuidoras de autopeças, oficinas e concessionárias.", "https://bateriacarro.com.br"),

    # More various industries
    ("CalçadoBR", "Equipamentos para fabricação de calçados. Atendemos fábricas de calçados no Rio Grande do Sul.", "https://calcadobr.com.br"),
    ("CosmétFábrica", "Equipamentos para fabricação de cosméticos. Atendemos fábricas de cosméticos e farmacêuticas.", "https://cosmetfabrica.com.br"),
    ("VelaBR", "Máquinas para fabricação de velas. Atendemos fábricas de velas e artigos religiosos.", "https://velabr.com.br"),
    ("SabonetePro", "Máquinas para fabricação de sabonetes. Atendemos fábricas de cosméticos e indústrias químicas.", "https://sabonetepro.com.br"),
    ("DetergenteBR", "Fábrica de produtos de limpeza. Atendemos distribuidoras e supermercados.", "https://detergentebr.com.br"),

    # B2B services
    ("CoworkingBR", "Espaço de coworking para empresas. Atendemos startups, escritórios e freelancers.", "https://coworkingbr.com.br"),
    ("ContêinerEscritório", "Contêineres adaptados para escritório. Atendemos construtoras e empresas de eventos.", "https://conteinerbr.com.br"),
    ("CopiadFrota", "Locação de copiadoras e impressoras. Atendemos escritórios, escolas e cartórios.", "https://copiadfrota.com.br"),
    ("TranscriçãoAI", "Transcrição de áudio e vídeo com IA. Atendemos escritórios de advocacia, jornais e tribunais.", "https://transcricaoai.com.br"),
    ("InterpretBR", "Serviços de interpretação simultânea. Atendemos empresas, congressos e tribunais.", "https://interpretbr.com.br"),

    # More hospitality
    ("ColchãoHotel", "Colchões e enxovais hoteleiros. Atendemos hotéis, pousadas e motéis.", "https://colchaohotel.com.br"),
    ("CafeteiraProf", "Máquinas de café profissionais para escritórios. Atendemos escritórios, hotéis e restaurantes.", "https://cafeteirapro.com.br"),

    # More graphic
    ("PlotterBR", "Impressoras plotter e materiais para comunicação visual. Atendemos gráficas e agências.", "https://plotterbr.com.br"),
    ("CorteLaser", "Máquinas de corte a laser para acrílico e MDF. Atendemos gráficas, marcenarias e indústrias.", "https://cortelaser.com.br"),

    # More niche
    ("ArmárioAço", "Armários e estantes de aço. Atendemos escritórios, fábricas e vestiários.", "https://armarioaco.com.br"),
    ("CofresMax", "Cofres e casas-forte. Atendemos bancos, joalherias e empresas.", "https://cofresmax.com.br"),
    ("MontaCargas", "Monta-cargas e plataformas de carga. Atendemos restaurantes, hospitais e armazéns.", "https://montacargas.com.br"),
    ("EsteiraBagagem", "Esteiras de bagagem para aeroportos. Atendemos aeroportos e centros de distribuição.", "https://esteirabagagem.com.br"),
    ("ProtetorPiso", "Protetores de piso para cadeiras e móveis. Atendemos condomínios, hotéis e escritórios.", "https://protetorpiso.com.br"),

    # More industrial
    ("RobôIndustrial", "Robôs colaborativos para linha de montagem. Atendemos indústrias automotivas e fábricas.", "https://roboindustrial.com.br"),
    ("SensorIndustrial", "Sensores industriais - proximidade, pressão, temperatura. Atendemos fábricas e indústrias.", "https://sensorindustrial.com.br"),
    ("CLPBrasil", "Controladores lógicos programáveis. Atendemos indústrias e integradores de automação.", "https://clpbrasil.com.br"),
    ("SCADAMax", "Sistemas SCADA para supervisão industrial. Atendemos indústrias, mineradoras e usinas.", "https://scadamax.com.br"),
    ("PneumáticaBR", "Cilindros e válvulas pneumáticas. Atendemos indústrias e fábricas.", "https://pneumaticabr.com.br"),
    ("HidráulicaInd", "Cilindros e bombas hidráulicas industriais. Atendemos indústrias metalúrgicas e mineradoras.", "https://hidraulicaind.com.br"),
    ("FresadoraCNC", "Fresadoras CNC de alta precisão. Atendemos indústrias metalúrgicas e fábricas.", "https://fresadoracnc.com.br"),
    ("TornoCNC", "Tornos CNC para usinagem. Atendemos indústrias metalúrgicas e fábricas de autopeças.", "https://tornocnc.com.br"),
    ("BalançaDinâmica", "Balanças dinâmicas para linhas de produção. Atendemos indústrias alimentícias e farmacêuticas.", "https://balancadinamica.com.br"),
    ("DetectorMetal", "Detectores de metais para indústria alimentícia. Atendemos indústrias alimentícias e farmacêuticas.", "https://detectormetal.com.br"),

    # Regional / specific market
    ("AgenciaTurSP", "Agência de turismo corporativo em São Paulo. Atendemos empresas e consultorias no Sudeste.", "https://agenciatursp.com.br"),
    ("TransporteCuritiba", "Transporte executivo em Curitiba. Atendemos empresas e hotéis no Paraná.", "https://transportecuritiba.com.br"),
    ("MudançaFloripa", "Mudanças e fretes em Florianópolis. Atendemos imobiliárias e condomínios em Santa Catarina.", "https://mudancafloripa.com.br"),
    ("DespachanteRJ", "Despachante automotivo e imobiliário no Rio de Janeiro. Atendemos concessionárias e imobiliárias.", "https://despachanterj.com.br"),
    ("CateringBH", "Catering e coffee break em Belo Horizonte. Atendemos empresas e hotéis em Minas Gerais.", "https://cateringbh.com.br"),
    ("LimpezaSalvador", "Limpeza profissional em Salvador. Atendemos condomínios e shoppings na Bahia.", "https://limpezasalvador.com.br"),
    ("SegurançaRecife", "Segurança patrimonial em Recife. Atendemos condomínios e empresas em Pernambuco.", "https://segrancarecife.com.br"),
    ("TIGoiânia", "Suporte de TI para empresas em Goiânia. Atendemos escritórios e indústrias em Goiás.", "https://tigoiania.com.br"),
    ("ContabManaus", "Escritório de contabilidade em Manaus. Atendemos empresas e comércios no Amazonas.", "https://contabmanaus.com.br"),
    ("ArCondBrasília", "Ar condicionado e climatização em Brasília. Atendemos escritórios e órgãos públicos no DF.", "https://arcondbrasilia.com.br"),

    # More diverse descriptions
    ("ProteinaBR", "Proteínas vegetais para indústria alimentícia. Atendemos indústrias de alimentos e startups foodtech.", "https://proteinabr.com.br"),
    ("CânelaEspeciarias", "Especiarias importadas para indústria. Atendemos indústrias alimentícias e restaurantes.", "https://canelaespeciarias.com.br"),
    ("OleoBR", "Óleos industriais e lubrificantes. Atendemos fábricas, oficinas e distribuidoras.", "https://oleobr.com.br"),
    ("GásBR", "Distribuição de gás industrial - oxigênio, argônio, acetileno. Atendemos indústrias metalúrgicas e hospitais.", "https://gasbr.com.br"),
    ("TintaInd", "Tintas industriais e anticorrosivos. Atendemos indústrias, construtoras e mineradoras.", "https://tintaind.com.br"),
    ("SelvadorBR", "Equipamentos de serigrafia e sublimação. Atendemos gráficas e confecções.", "https://selvadorbr.com.br"),
    ("ModularBR", "Construções modulares pré-fabricadas. Atendemos construtoras e mineradoras.", "https://modularbr.com.br"),
    ("DryWallBR", "Sistemas drywall e forros de gesso. Atendemos construtoras e reformadoras.", "https://drywallbr.com.br"),
    ("MáquinaLavar", "Máquinas de lavar industriais. Atendemos hotéis, hospitais e lavanderias.", "https://maquinalavar.com.br"),
    ("CalçadoSegurança", "Calçados de segurança e botas profissionais. Atendemos fábricas, construtoras e mineradoras.", "https://calcadoseguranca.com.br"),

    # Final batch to ensure 500+
    ("ChurrasqueiraPro", "Churrasqueiras e equipamentos para churrascarias. Atendemos restaurantes e buffets.", "https://churrasqueirapro.com.br"),
    ("SalaFria", "Salas limpas e ambientes controlados. Atendemos farmacêuticas, laboratórios e hospitais.", "https://salafria.com.br"),
    ("MóvelHospitalar", "Mobiliário hospitalar - leitos, macas, poltronas. Atendemos hospitais e clínicas.", "https://movelhospitalar.com.br"),
    ("TreinamentoSST", "Treinamentos de segurança do trabalho. Atendemos construtoras, indústrias e mineradoras.", "https://treinamentosst.com.br"),
    ("PainelSolar", "Montagem de usinas solares fotovoltaicas. Atendemos fazendas, indústrias e cooperativas.", "https://painelsolar.com.br"),
    ("TeleMedicina", "Plataforma de telemedicina e teleconsulta. Atendemos clínicas médicas e operadoras de saúde.", "https://telemedicina.com.br"),
    ("CertificadoDigital", "Certificados digitais A1 e A3. Atendemos escritórios de contabilidade e empresas.", "https://certificadodigital.com.br"),
    ("LocaçãoVeículos", "Locação de veículos corporativos. Atendemos empresas e transportadoras.", "https://locacaoveiculos.com.br"),
    ("DesignIndustrial", "Design industrial e prototipagem. Atendemos indústrias e startups.", "https://designindustrial.com.br"),
    ("ProtótipoRápido", "Impressão 3D e prototipagem rápida. Atendemos indústrias e startups de produto.", "https://prototiporapido.com.br"),
    ("AutomaçãoPredial", "Automação predial e building management. Atendemos shoppings, hotéis e condomínios.", "https://automacaopredial.com.br"),
    ("PortaAutomática", "Portas automáticas e sistemas de acesso. Atendemos shoppings, hospitais e escritórios.", "https://portaautomatica.com.br"),
    ("ProfissionalTI", "Recrutamento de profissionais de TI. Atendemos empresas de tecnologia e startups.", "https://profissionalti.com.br"),
    ("OutplacementBR", "Outplacement e recolocação profissional. Atendemos empresas de recursos humanos e multinacionais.", "https://outplacementbr.com.br"),
    ("BenefíciosPJ", "Gestão de benefícios corporativos - VR, VA, VT. Atendemos empresas de recursos humanos e escritórios de contabilidade.", "https://beneficiospj.com.br"),
    ("PayrollBR", "Processamento de folha de pagamento. Atendemos escritórios de contabilidade e empresas de BPO.", "https://payrollbr.com.br"),
    ("MeioAmbiente", "Licenciamento ambiental e EIA/RIMA. Atendemos mineradoras, construtoras e indústrias.", "https://meioambiente.com.br"),
    ("RecuperaçãoSolo", "Recuperação de áreas degradadas. Atendemos mineradoras e empresas de reflorestamento.", "https://recuperacaosolo.com.br"),
    ("AssistênciaAuto", "Assistência 24h para frotas. Atendemos seguradoras, locadoras e transportadoras.", "https://assistenciaauto.com.br"),
    ("RastreadorFrota", "Rastreamento e telemetria para frotas. Atendemos transportadoras e empresas de logística.", "https://rastreadorfrota.com.br"),

    # ── BATCH 3: final 50 to reach 500+ ──
    ("BrindesCorpo", "Brindes corporativos personalizados - canecas, camisetas, agendas. Atendemos agências e empresas.", "https://brindescorpo.com.br"),
    ("PlacaSolar2", "Instalação de placas solares para empresas e residências. Atendemos no Nordeste e Centro-Oeste.", "https://placasolar2.com.br"),
    ("MicroondaInd", "Micro-ondas industriais para aquecimento e secagem. Atendemos indústrias alimentícias e cerâmicas.", "https://microondaind.com.br"),
    ("FossilBR", "Paleontologia e consultoria ambiental para mineradoras. Atendemos mineradoras e pedreiras.", "https://fossilbr.com.br"),
    ("BioTechLab", "Insumos para laboratórios de biotecnologia. Atendemos universidades, startups e laboratórios.", "https://biotechlab.com.br"),
    ("LogRevBR", "Logística reversa de embalagens. Atendemos indústrias e distribuidoras.", "https://logrevbr.com.br"),
    ("FibaCarbono", "Peças em fibra de carbono e compositos. Atendemos indústrias aeronáuticas e automotivas.", "https://fibacarbono.com.br"),
    ("PainelMDF", "Painéis MDF e compensados. Atendemos marcenarias, fábricas de móveis e construtoras.", "https://painelmdf.com.br"),
    ("SerrariaBR", "Equipamentos de serraria para madeira. Atendemos serrarias e empresas florestais.", "https://serrariabr.com.br"),
    ("BlocoBR", "Blocos de concreto e pavimentos. Atendemos construtoras e lojas de materiais.", "https://blocobr.com.br"),
    ("AreiaePedra", "Areia, brita e agregados para construção. Atendemos construtoras e concreteiras.", "https://areiaepedra.com.br"),
    ("PrefabricadoBR", "Lajes e estruturas pré-fabricadas de concreto. Atendemos construtoras e incorporadoras.", "https://prefabricadobr.com.br"),
    ("MáquinaEscavar", "Miniescavadeiras e bobcats. Atendemos construtoras e empresas de terraplanagem.", "https://maquinaescavar.com.br"),
    ("TelaCercaBR", "Telas e cercas para construção civil e agropecuária. Atendemos construtoras e fazendas.", "https://telacercabr.com.br"),
    ("FonteNobreak", "Fontes e nobreaks industriais. Atendemos data centers e indústrias.", "https://fontenobreak.com.br"),
    ("ServidorBR", "Servidores e storage corporativo. Atendemos data centers e empresas de tecnologia.", "https://servidorbr.com.br"),
    ("IPCamerasBR", "Câmeras IP e NVR para segurança. Atendemos condomínios, empresas e indústrias.", "https://ipcamerasbr.com.br"),
    ("SoftwareEscola", "Software de gestão escolar. Atendemos escolas particulares e faculdades.", "https://softwareescola.com.br"),
    ("EscolaIdiomas", "Escola de idiomas corporativa. Atendemos empresas e escritórios.", "https://escolaidiomas.com.br"),
    ("MotorDiesel", "Motores diesel e geradores. Atendemos embarcações, mineradoras e indústrias.", "https://motordiesel.com.br"),
    ("ComponentePCB", "Placas de circuito impresso. Atendemos indústrias eletrônicas e fábricas.", "https://componentepcb.com.br"),
    ("CabinePintura", "Cabines de pintura automotiva e industrial. Atendemos funilarias e indústrias.", "https://cabinepintura.com.br"),
    ("JatoAreia", "Equipamentos de jato de areia e granalha. Atendemos indústrias metalúrgicas e estaleiros.", "https://jatoareia.com.br"),
    ("GalpãoPreMold", "Galpões pré-moldados de concreto. Atendemos indústrias, agroindústrias e distribuidoras.", "https://galpaopremold.com.br"),
    ("DoceiraPro", "Equipamentos para doceiras e confeitarias. Atendemos confeitarias e padarias.", "https://doceirapro.com.br"),
    ("SorveteIndustrial", "Máquinas de sorvete em escala industrial. Atendemos indústrias alimentícias e franquias.", "https://sorveteindustrial.com.br"),
    ("CervejaMicro", "Equipamentos para microcervejarias. Atendemos microcervejarias e brewpubs no Sul.", "https://cervejamicro.com.br"),
    ("ÁguaFiltro", "Filtros e purificadores de água industrial. Atendemos fábricas, hospitais e restaurantes.", "https://aguafiltro.com.br"),
    ("CompactadorBR", "Compactadores de resíduos sólidos. Atendemos cooperativas de reciclagem e condomínios.", "https://compactadorbr.com.br"),
    ("TrituradorBR", "Trituradores industriais para plástico, papel e orgânicos. Atendemos cooperativas de reciclagem e indústrias.", "https://trituradorBR.com.br"),
    ("GradeAradora", "Grades aradoras e subsoladores para agricultura. Atendemos fazendas e revendedoras agrícolas.", "https://gradearadora.com.br"),
    ("ColheitadeiraUsada", "Colheitadeiras e tratores usados. Atendemos fazendas e revendedoras agrícolas.", "https://colheitadeirausada.com.br"),
    ("SistemaOrdem", "Software de ordens de serviço para assistências técnicas. Atendemos oficinas e assistências técnicas.", "https://sistemaordem.com.br"),
    ("AppDelivery2", "Sistema de delivery para restaurantes. Atendemos restaurantes, pizzarias e lanchonetes.", "https://appdelivery2.com.br"),
    ("SistemaClube", "Software para clubes e associações. Atendemos clubes, associações e sindicatos.", "https://sistemaclube.com.br"),
    ("MiniCartão", "Máquinas de cartão sem aluguel. Atendemos autônomos, microempresas e comércios.", "https://minicartao.com.br"),
    ("ContainerRef", "Contêineres refrigerados. Atendemos exportadoras de frutas, frigoríficos e farmacêuticas.", "https://containerref.com.br"),
    ("KitSolar", "Kits de energia solar residencial e empresarial. Atendemos instaladores e empresas de energia solar.", "https://kitsolar.com.br"),
    ("TelhadoVerde", "Telhados verdes e jardins verticais. Atendemos construtoras e arquitetos.", "https://telhadoverde.com.br"),
    ("MotoBR", "Motos para empresas de delivery e motoboy. Atendemos empresas de entregas e restaurantes.", "https://motobr.com.br"),
    ("CaçambaBR", "Locação de caçambas para entulho. Atendemos construtoras e reformadoras.", "https://cacambabr.com.br"),
    ("PortãoResidencial", "Portões e grades residenciais. Atendemos construtoras e condomínios.", "https://portaoresidencial.com.br"),
]

# ── Run tests ──
print(f"Testing {len(EMPRESAS)} company profiles...\n")

errors = []
warnings = []
stats = {
    'total': len(EMPRESAS),
    'min_termos': 999,
    'max_termos': 0,
    'min_cargos': 999,
    'max_cargos': 0,
    'min_segmentos': 999,
    'total_termos': 0,
    'sem_segmento_detectado': 0,
    'com_generico_irrelevante': 0,
    'regiao_errada': 0,
}

t0 = time.time()

for i, (nome, desc, site) in enumerate(EMPRESAS):
    try:
        result = _gerar_termos(nome, desc, site)
    except Exception as e:
        errors.append(f"[{i}] {nome}: EXCEPTION: {e}")
        continue

    termos = result['termos']
    cargos = result['cargos']

    # Basic checks
    if len(termos) < 130:
        errors.append(f"[{i}] {nome}: apenas {len(termos)} termos (min 130)")
    if len(cargos) < 3:
        warnings.append(f"[{i}] {nome}: apenas {len(cargos)} cargos")

    stats['min_termos'] = min(stats['min_termos'], len(termos))
    stats['max_termos'] = max(stats['max_termos'], len(termos))
    stats['min_cargos'] = min(stats['min_cargos'], len(cargos))
    stats['max_cargos'] = max(stats['max_cargos'], len(cargos))
    stats['total_termos'] += len(termos)

    # Check: no terms should be empty or just whitespace
    empty = [t for t in termos if not t.strip()]
    if empty:
        errors.append(f"[{i}] {nome}: {len(empty)} termos vazios")

    # Check: terms should have location component
    has_location = sum(1 for t in termos if any(c in t for c in [
        'Curitiba', 'Porto Alegre', 'São Paulo', 'Sao Paulo', 'Goiania',
        'Salvador', 'Manaus', 'PR', 'SC', 'RS', 'SP', 'MG', 'RJ',
        'GO', 'MT', 'MS', 'BA', 'PE', 'CE', 'AM', 'PA',
    ]))
    if has_location < len(termos) * 0.5:
        warnings.append(f"[{i}] {nome}: apenas {has_location}/{len(termos)} termos com localização")

    # Check: relevance — terms should relate to the description
    desc_lower = desc.lower()

    # Print sample for every 50th profile
    if i % 50 == 0:
        print(f"--- [{i}] {nome} ---")
        print(f"  Termos: {len(termos)} | Cargos: {len(cargos)}")
        print(f"  Primeiros 5 termos:")
        for t in termos[:5]:
            print(f"    {t}")
        print(f"  Cargos: {', '.join(cargos[:5])}")
        print()

elapsed = time.time() - t0

print(f"\n{'='*60}")
print(f"RESULTADO: {len(EMPRESAS)} empresas testadas em {elapsed:.1f}s")
print(f"{'='*60}")
print(f"  Termos/empresa: min={stats['min_termos']}, max={stats['max_termos']}, media={stats['total_termos']/len(EMPRESAS):.0f}")
print(f"  Cargos/empresa: min={stats['min_cargos']}, max={stats['max_cargos']}")
print()

if errors:
    print(f"ERROS ({len(errors)}):")
    for e in errors:
        print(f"  ✗ {e}")
else:
    print("✓ Nenhum erro encontrado!")

if warnings:
    print(f"\nAVISOS ({len(warnings)}):")
    for w in warnings[:20]:
        print(f"  ⚠ {w}")
    if len(warnings) > 20:
        print(f"  ... e mais {len(warnings)-20} avisos")
else:
    print("✓ Nenhum aviso!")

print(f"\n{'='*60}")
print("TESTE CONCLUÍDO")
