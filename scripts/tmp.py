import pandas as pd

# Volvemos a cargar el dataframe original
df = pd.read_csv('implementacion/al_fuego/outputs/vista_previa_enriquecimiento.csv')

# 1. Correcciones de descripciones graves (Alucinaciones de producto)
# AFCE0103 - Bondiola Magret EV (Era de cerdo, no de pato)
df.loc[df['codigo_producto'] == 'AFCE0103', 'descripcion_mejorada'] = (
    "Bondiola de cerdo de la marca Magret, envasada al vacío. Presenta un excelente marmoleo de grasa "
    "que aporta una jugosidad única, siendo ideal para asar a la parrilla, cocinar al horno o preparar a la cerveza."
)
df.loc[df['codigo_producto'] == 'AFCE0103', 'alias_propuestos'] = "bondiola|bondiola de cerdo|magret|fiambre"

# AFTE0067 - Media Luna De Vacio (Es un corte de carne, no una bolsa plástica)
df.loc[df['codigo_producto'] == 'AFTE0067', 'descripcion_mejorada'] = (
    "Corte de carne vacuna correspondiente a la sección interna del vacío, caracterizado por su forma semicircular, "
    "textura jugosa y sabor pronunciado. Un clásico de la parrilla argentina, ideal para cocinar a fuego lento con brasas."
)
df.loc[df['codigo_producto'] == 'AFTE0067', 'alias_propuestos'] = "media luna|vacío|corte de carne|parrilla"

# AFTE0023 - Tomahawk (Es un corte premium, no un hacha de camping)
df.loc[df['codigo_producto'] == 'AFTE0023', 'descripcion_mejorada'] = (
    "Corte de carne vacuna premium tipo ojo de bife con el hueso de la costilla entero y limpio. "
    "Su gran infiltración de grasa intramuscular garantiza una experiencia jugosa y de tierno sabor, ideal para lucirse en la parrilla."
)
df.loc[df['codigo_producto'] == 'AFTE0023', 'alias_propuestos'] = "tomahawk|ojo de bife|corte premium|asado"

# AFTE0086 - Lomo Estancia CP (Es de novillo/vacuno, no de cerdo)
df.loc[df['codigo_producto'] == 'AFTE0086', 'descripcion_mejorada'] = (
    "Lomo vacuno premium de la marca Estancia CP, envasado al vacío. Un corte de carne extremadamente tierno, magro y selecto, "
    "perfecto para asar entero a la parrilla, cocinar al horno o cortar en bifes gruesos."
)
df.loc[df['codigo_producto'] == 'AFTE0086', 'alias_propuestos'] = "lomo|lomo vacuno|estancia cp|carne tierna"

# VACO0024 - Atun rojo Fazzio (Es filet fresco/congelado, no enlatado)
df.loc[df['codigo_producto'] == 'VACO0024', 'descripcion_mejorada'] = (
    "Filet de atún rojo fresco de la marca Fazzio, seleccionado de alta calidad y envasado al vacío para garantizar su pureza. "
    "Con un excelente aporte proteico, es ideal para sellar a la parrilla, cocinar a la plancha o preparar platos gourmet."
)
df.loc[df['codigo_producto'] == 'VACO0024', 'alias_propuestos'] = "atún|atún rojo|pescado|fazzio"

# VACO0045 - Planchetita con tapa El Mansero (Es un accesorio de herrería para asador, no carne vacuna)
df.loc[df['codigo_producto'] == 'VACO0045', 'descripcion_mejorada'] = (
    "Plancha de hierro con tapa de la marca El Mansero, diseñada especialmente para cocinar carnes, vegetales o hamburguesas "
    "directamente sobre la hornalla, la parrilla o las brasas, logrando una cocción pareja y reteniendo los jugos."
)
df.loc[df['codigo_producto'] == 'VACO0045', 'alias_propuestos'] = "plancheta|planchetita|el mansero|bazar"

# VACO0053 - Set Tramontina El Mansero (Son cubiertos de asado, no herramientas de jardinería)
df.loc[df['codigo_producto'] == 'VACO0053', 'descripcion_mejorada'] = (
    "Set de cubiertos premium para asado de la marca Tramontina con terminaciones exclusivas de El Mansero. "
    "Incluye un cuchillo de carne de alta precisión y un tenedor trinchante, indispensables para cualquier asador."
)
df.loc[df['codigo_producto'] == 'VACO0053', 'alias_propuestos'] = "set de cubiertos|tramontina|el mansero|cuchillo de asado"

# VACO0023 - Arrollados de pollo FazzioFazzio (Quitar la palabra "chacinados" que confunde el rubro de pescadería de Fazzio)
df.loc[df['codigo_producto'] == 'VACO0023', 'descripcion_mejorada'] = (
    "Arrollados de pollo elaborados con pechuga de alta calidad, sazonados y enrollados, envasados al vacío para una óptima conservación. "
    "Una opción práctica y sabrosa para resolver tus comidas o sumar a una picada variada."
)
df.loc[df['codigo_producto'] == 'VACO0023', 'alias_propuestos'] = "arrollado|pollo arrollado|arrollado de pollo"

# 2. Correcciones de orígenes e ingredientes erróneos
# VACO0132 - Chaman Red Blend (Es de Mendoza, no de Chile)
df.loc[df['codigo_producto'] == 'VACO0132', 'descripcion_mejorada'] = (
    "Vino tinto tipo Red Blend de la bodega Chamán, originario del prestigioso Valle de Uco en Mendoza, Argentina. "
    "Presenta una cuidada combinación de variedades que aportan complejidad, estructura y un final elegante, ideal para acompañar carnes asadas."
)

# VACO0114 y VACO0116 - Domaine Edem (Son cervezas artesanales belgas, no espumantes de uva)
df.loc[df['codigo_producto'] == 'VACO0114', 'descripcion_mejorada'] = (
    "Cerveza artesanal premium de estilo belga Domaine Edem Blonde. Presenta un color dorado brillante, un perfil "
    "maltoso equilibrado con sutiles notas cítricas y un amargor sumamente refrescante. Ideal para acompañar picadas y platos ligeros."
)
df.loc[df['codigo_producto'] == 'VACO0114', 'alias_propuestos'] = "cerveza|birra|rubia|blonde|domaine edem"

df.loc[df['codigo_producto'] == 'VACO0116', 'descripcion_mejorada'] = (
    "Cerveza artesanal premium de la línea Domaine Edem No7. Elaborada bajo recetas tradicionales con una meticulosa selección "
    "de lúpulos y maltas, ofrece un cuerpo robusto y un perfil de sabor complejo ideal para paladares exigentes y maridajes gastronómicos."
)
df.loc[df['codigo_producto'] == 'VACO0116', 'alias_propuestos'] = "cerveza|birra|domaine edem"

# AFDE0091 - Molinillo Sal Marina Gruesa (Quitar origen delta del Ebro, España)
df.loc[df['codigo_producto'] == 'AFDE0091', 'descripcion_mejorada'] = (
    "Molinillo de sal marina gruesa natural y pura de 110 gramos, ideal para sazonar tus cortes a la parrilla. "
    "Su práctico molinillo regulable permite una dosificación precisa sobre carnes y vegetales directamente antes de servir."
)

# VACO0205 - 7up 500ml (Es de PepsiCo, no de Coca-Cola Company)
df.loc[df['codigo_producto'] == 'VACO0205', 'descripcion_mejorada'] = (
    "Bebida gaseosa sabor lima-limón en botella de 500 ml, transparente, refrescante y con el clásico toque cítrico ideal para consumir sola o como mezclador."
)

# 3. Limpieza masiva de alias "chinchu" infiltrados en cortes de carne vacuna que no corresponden
def limpiar_alias_chinchu(row):
    alias = str(row['alias_propuestos'])
    if row['codigo_producto'] != 'AFTE0020' and 'AFTE0020' not in str(row['codigo_producto']): # No tocar el chinchulín real
        lista_alias = [a.strip() for a in alias.split('|') if a.strip() not in ['chinchu', 'chinchulín', 'chinchulines']]
        return "|".join(lista_alias)
    return alias

df['alias_propuestos'] = df.apply(limpiar_alias_chinchu, axis=1)

# Limpieza manual de los alias específicos colados
df.loc[df['codigo_producto'] == 'AFEL0051', 'alias_propuestos'] = "hamburguesa|burger|medallón" # Quitar panchito
df.loc[df['codigo_producto'] == 'AFBE0013', 'alias_propuestos'] = "gaseosa pomelo|pomelo|schweppes" # Quitar agua tónica
df.loc[df['codigo_producto'] == 'AFVA0100', 'alias_propuestos'] = "pastillas para encender|encendedores|iniciador" # Quitar fuegos artificiales

# Guardar el archivo corregido
output_filename = 'vista_previa_enriquecimiento_arreglado.csv'
df.to_csv(output_filename, index=False)
print(f"Archivo guardado exitosamente como: {output_filename}")