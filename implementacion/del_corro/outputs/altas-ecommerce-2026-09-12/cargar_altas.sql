-- Tenant: del_corro
-- Altas e-commerce Centralo 2026-09-12
-- Inserta solo suffix10 que NO existen (excluye dup-merged-*).
-- Etiqueta y agrupa todos los destinos únicos para plantilla clientes_web.

WITH excel_raw(
  suffix10, phone_canon, nombre, nombre_de_pila, email, direccion, cuit,
  dni, tipo_doc, codigo_centralo
) AS (
  VALUES
  ('3517309273', '5493517309273', 'aldana gacitua', 'aldana', 'aldanagacitua98@gmail.com', 'Río Negro 1227, X5003DDC Córdoba, Argentina', NULL, '40901899', 'DNI', 446888),
  ('3571419486', '5493571419486', 'Adolfo Dominguez', 'Adolfo', 'servicead109@gmail.com', 'Cerro Pan de Azucar, X5856 Embalse, Córdoba, Argentina', NULL, '22521109', 'DNI', 446607),
  ('3512462133', '5493512462133', 'Agustin Abregu', 'Agustin', 'agusabregu2008x@gmail.com', 'Alejandro Humboldt, X5021 Córdoba, Argentina', NULL, '47578447', 'DNI', 446459),
  ('3518003940', '5493518003940', 'lenny carrasco', 'lenny', 'carrascolennysimon@gmail.com', 'Tristan de Tejeda 638, X5008 Córdoba, Argentina', NULL, '46450731', 'DNI', 446059),
  ('3513995470', '5493513995470', 'Yuliana esconar', 'Yuliana', 'yulianasabrinaescobar94@gmail.com', 'Puvr Adrian Escobar 3150, X5016 Córdoba, Argentina', NULL, '38555335', 'DNI', 445770),
  ('3876580680', '5493876580680', 'Ayuzo Ayuzo', 'Ayuzo', 'claudy.ayuzo@gmail.com', 'RP1, Salta, Argentina', NULL, '28151262', 'DNI', 445583),
  ('2994688268', '5492994688268', 'Patricia Asencio', 'Patricia', 'patriciaandreafra@gmail.com', 'Manuel Bello 2419, Neuquén, Argentina', NULL, '32090697', 'DNI', 445537),
  ('3516583900', '5493516583900', 'joni gonzalez', 'joni', 'jonigonzalez07@gmail.com', 'Ambrosio Funes 2917, X5014JGG Córdoba, Argentina', NULL, '39303025', 'DNI', 445471),
  ('2804205363', '5492804205363', 'Mariana Alfaro', 'Mariana', 'alfaromariana508@gmail.com', 'Cecilio di Clemente 1076, U9120 Puerto Madryn, Chubut, Argentina', NULL, '39441665', 'DNI', 445453),
  ('3549631689', '5493549631689', 'Leonardo aliendro', 'Leonardo', 'leospc22@gmail.com', 'Cruz del Eje, X5017 Córdoba, Argentina', NULL, '38251432', 'DNI', 445448),
  ('3574416776', '5493574416776', 'Marcia Brochero', 'Marcia', 'brocheromarcia3@gmail.com', 'Nicolás Avellaneda, X5000 Córdoba, Argentina', NULL, '34970038', 'DNI', 445447),
  ('3512271233', '5493512271233', 'Sofia Siragusa', 'Sofia', 'lasoso.ss@gmail.com', 'calle 3, Potrero de Garay, Cordoba sn, 5189 Córdoba, Córdoba, Argentina', NULL, '39305961', 'DNI', 445356),
  ('2665056940', '5492665056940', 'Antonella Oros', 'Antonella', 'olucianaantonella@gmail.com', 'San Francisco, D5700 San Luis, Argentina', NULL, '42065872', 'DNI', 445312),
  ('3804775006', '5493804775006', 'Belén Solohaga', 'Belén', 'solohagabelen21@gmail.com', 'Aimogasta, F5302 La Rioja, Argentina', NULL, '35541137', 'DNI', 445274),
  ('3515607683', '5493515607683', 'melisa conrad', 'melisa', 'melisa.conrad@hotmail.com', 'Correa de Saá 2557, X5012 Córdoba, Argentina', NULL, '38332803', 'DNI', 445132),
  ('3573410894', '5493573410894', 'irene del valle krenz', 'irene', 'irenekrenz1982@gmail.com', 'Blvd. Juan Bautista Alberdi 655, X5972 Pilar, Córdoba, Argentina', NULL, '29353077', 'DNI', 444889),
  ('3541294674', '5493541294674', 'Mariana Garro', 'Mariana', 'lunilujancho@gmail.com', 'Rio Yuspe 1719, X5158 Córdoba, Córdoba, Argentina', NULL, '28377936', 'DNI', 444669),
  ('3512110786', '5493512110786', 'Alberto leyria', 'Alberto', 'al0403@yahoo.com.ar', 'Francisco Tamburini 6977, X5021 Córdoba, Argentina', NULL, '14005122', 'DNI', 444558),
  ('3468600668', '5493468600668', 'Agostina pelayes', 'Agostina', 'agostinapelayes11@gmail.com', 'Monte Maíz, X5113, Córdoba, Argentina', NULL, '43883049', 'DNI', 444048),
  ('3543581335', '5493543581335', 'ANABELA BARRIOS', 'ANABELA', 'drickacasacentral@gmail.com', 'Av. de Circunvalación Agustín Tosco, Córdoba, Argentina', NULL, '30577988', 'DNI', 444041),
  ('3517517064', '5493517517064', 'celeste felicia', 'celeste', 'veinte016@gmail.com', 'Blvr. Chacabuco 232, X5000 Córdoba, Argentina', '27423836453', NULL, 'CUIT', 441825),
  ('3525621357', '5493525621357', 'gabri TREJO', 'gabri', 'kioscolodefacu2022@gmail.com', 'San Juan Nte. 516, X5220 Jesus María, Córdoba, Argentina', NULL, '43606076', 'DNI', 441444),
  ('3513848901', '5493513848901', 'franco bongiovanni', 'franco', 'francodb.181@gmail.com', 'Paraná 326, X5000 HXH, Córdoba, Argentina', NULL, '36833079', 'DNI', 441345),
  ('3515999481', '5493515999481', 'Maria Gabriela Valdez', 'Maria', 'mariagabrielavaldez91@gmail.com', 'Humahuaca, X5155, Córdoba, Argentina', NULL, '36009194', 'DNI', 440089),
  ('3513046034', '5493513046034', 'Karin Vaca', 'Karin', 'karinvaca8@gmail.com', 'La Cordillera 4246, X5009EJV Córdoba, Argentina', NULL, '27208731314', 'DNI', 439747),
  ('3517342425', '5493517342425', 'Sergio González', 'Sergio', 'sergiogonzalezcba7@gmail.com', 'Los Ticas, X5001 Córdoba, Argentina', NULL, '17383205', 'DNI', 439392),
  ('3512487854', '5493512487854', 'noelia Perez Gormaz', 'noelia', 'nperezgormaz@gmail.com', 'Sgto. Cabral 2065, X5014 Córdoba, Argentina', NULL, '30.579.653', 'DNI', 438979),
  ('3541683742', '5493541683742', 'Cristian  Nickus', 'Cristian', 'nickuscristian@gmail.com', 'Sarasate 292, X5152 Villa Carlos Paz, Córdoba, Argentina', '20231716336', NULL, 'CUIT', 437987),
  ('3517035199', '5493517035199', 'karem sarai nieva', 'karem', 'sarainieva22@gmail.com', 'Dr. Juan F. Cafferata 474, X5003FZJ Córdoba, Argentina', NULL, '38648011', 'DNI', 435921),
  ('3584296555', '5493584296555', 'Gabriel Carranza', 'Gabriel', 'gabriel.carranza1994@gmail.com', 'Guillermo Reyna, X5002 Córdoba, Argentina', NULL, '38418203', 'DNI', 435777),
  ('3826406601', '5493826406601', 'Mariana Sosa', 'Mariana', 'marianasosa0929@gmail.com', 'Las Talas, La Rioja, Argentina', NULL, '39324140', 'DNI', 435600),
  ('3515508664', '5493515508664', 'dayana Clerici', 'dayana', 'dayana.clerici@gmail.com', 'Avenida Bodereau 7450, X5018 Córdoba, Argentina', NULL, '35785597', 'DNI', 434901),
  ('3513481647', '5493513481647', 'maria jose sosa', 'maria', 'joshela1565@gmail.com', 'Carlos O. Bunge 4077, X5016 Córdoba, Argentina', NULL, '28535980', 'DNI', 434398),
  ('3516696102', '5493516696102', 'Elizabeth Luna', 'Elizabeth', 'autoserviciopleno@hotmail.com', 'Tte. Melchor Escola, X5019 Córdoba, Argentina', NULL, '32540339', 'DNI', 434380),
  ('3516426138', '5493516426138', 'Natasha Tapia', 'Natasha', 'natashatapia2002@gmail.com', 'Gral. Paz 186, X5022 Córdoba, Argentina', NULL, '43927093', 'DNI', 433271),
  ('3516761137', '5493516761137', 'cielo gomez', 'cielo', 'mariacielogomezoliveto@outlook.com', 'Agustín Garzón 2695, X5006GGE Córdoba, Argentina', NULL, '32239795', 'DNI', 433011),
  ('3516818195', '5493516818195', 'marianella seguel', 'marianella', 'marianellaseguel25@gmail.com', 'N. Rodríguez Peña, X5000 Córdoba, Argentina', NULL, '37056176', 'DNI', 431848),
  ('3515582302', '5493515582302', 'Ellas Correa', 'Ellas', 'elias.j.correa2014@gmail.com', 'Blvd. Pres. Dr. Arturo U. Illia 520, X5000ASS Córdoba, Argentina', NULL, '42854715', 'DNI', 430629),
  ('3518573859', '5493518573859', 'elsa Yaneth contramaestre Villalba', 'elsa', 'yanethcontra26@gmail.com', 'Simon Bolivar 600, X5843 Adelia María, Córdoba, Argentina', NULL, '95648900', 'DNI', 429719),
  ('3525541960', '5493525541960', 'nuria alejandra amuchastegui', 'nuria', 'nuriaamuchastegui@yahoo.com.ar', 'C. 51 371, X5223 Col. Caroya, Córdoba, Argentina', NULL, '25888994', 'DNI', 429521),
  ('3517911009', '5493517911009', 'david yorio', 'david', 'david.yorio@hotmail.com', 'Chubut 95, X5003 X5000LYB, Córdoba, Argentina', '20338316195', NULL, 'CUIT', 429023),
  ('3513761182', '5493513761182', 'Sonia Criado', 'Sonia', 'soniaalejandra.criado@gmail.com', 'Alejandro Humboldt 7095, X5021 Córdoba, Argentina', NULL, '32157148', 'DNI', 428142),
  ('3513417500', '5493513417500', 'Leonardo Romero', 'Leonardo', 'lromero.eltio@gmail.com', 'Suipacha 4291, X5012 Córdoba, Argentina', NULL, '29030043', 'DNI', 427767),
  ('3512011040', '5493512011040', 'Ezequiel Di Leo', 'Ezequiel', 'edileo77@gmail.com', 'Valencia 1436, X5014 Córdoba, Argentina', NULL, '34130046', 'DNI', 427622),
  ('3513924724', '5493513924724', 'Romina Aliendo', 'Romina', 'rominaaliendo@gmail.com', 'Calle Rodríguez Peña 39, X5168 Valle Hermoso, Córdoba, Argentina', NULL, '33034392', 'DNI', 427185),
  ('3515198905', '5493515198905', 'gabriela Perez', 'gabriela', 'fliataborda@live.com', 'Burruyaco 4668, X5017 Córdoba, Córdoba, Argentina', NULL, '23429961', 'DNI', 426988),
  ('3518105148', '5493518105148', 'Franco Agustin Aguero', 'Franco', 'francoagustinaguero1994@gmail.com', 'Eugenio de Igarzabal 517, X5017 Córdoba, Argentina', NULL, '38645327', 'DNI', 426703),
  ('3513803042', '5493513803042', 'Marianel Fernández', 'Marianel', 'pinoc994@gmail.com', 'Pedro Sanguinetto, X5012 Córdoba, Argentina', NULL, '39610142', 'DNI', 426007),
  ('3516194046', '5493516194046', 'juan ermeninto', 'juan', 'lulumar@live.com.ar', 'R. Balbin, Villa Allende, Córdoba, Argentina', NULL, '14659796', 'DNI', 425679),
  ('3517463571', '5493517463571', 'antonella lazarte', 'antonella', 'antonellalazarte1122@gmail.com', 'Italia 389, X5980 Oliva, Córdoba, Argentina', NULL, '41648109', 'DNI', 425449),
  ('3518110829', '5493518110829', 'Carla Denett', 'Carla', 'bycarladenett@hotmail.com', 'Henry Arán 2657, X5014 Córdoba, Argentina', NULL, '18813150', 'DNI', 425444),
  ('3546401209', '5493546401209', 'Bren Salomone', 'Bren', 'salomonebren@gmail.com', 'José Santos Chocano 4780, X5019 Córdoba, Argentina', NULL, '40577084', 'DNI', 424368),
  ('3544407285', '5493544407285', 'Magali Ledesma', 'Magali', 'magaliledesma462@gmail.com', 'Panaholma, X5012 Córdoba, Argentina', NULL, '44024063', 'DNI', 424365),
  ('3512574153', '5493512574153', 'sofia pinta', 'sofia', 'brendapinta@hotmail.com', 'La Cordillera 4130, X5009 Córdoba, Argentina', '27384136570', NULL, 'CUIT', 424339),
  ('3563402623', '5493563402623', 'RAUL CARDO', 'RAUL', 'huelladeluz28@hotmail.com', 'Urquiza 428, X5143 Miramar de Ansenuza, Córdoba, Argentina', NULL, '17583125', 'DNI', 424185),
  ('3512024431', '5493512024431', 'Laura Cabanay', 'Laura', 'laudv.c@gmail.com', 'Tucumán 281, X5022FKE Córdoba, Argentina', NULL, '39008508', 'DNI', 423913),
  ('3516135698', '5493516135698', 'natalia perez', 'natalia', 'nataliainesperez@hotmail.com', 'Sarmiento 652, X5151 La Calera, Córdoba, Argentina', NULL, '27311918619', 'DNI', 423800),
  ('3548553335', '5493548553335', 'nabila aburmeihle', 'nabila', 'matias97bonfiglio@gmail.com', 'Av. Gral. Paz 920, X5168 Valle Hermoso, Córdoba, Argentina', NULL, '40906432', 'DNI', 423568),
  ('3576412998', '5493576412998', 'josua arguello', 'josua', 'josuabergese@gmail.com', 'Arroyito, Córdoba, Argentina', NULL, '36621073', 'DNI', 423546),
  ('3516667978', '5493516667978', 'Maria Noel Montes de Oca', 'Maria', 'noelmdeo@gmail.com', 'Juan Perazo 4706, X5009 Córdoba, Argentina', '27280707320', NULL, 'CUIT', 423532),
  ('3518656344', '5493518656344', 'zaira Martinez', 'zaira', 'zaira2004martinez@gmail.com', 'Luis Burela 2941, X5006 Córdoba, Argentina', NULL, '46127924', 'DNI', 423080),
  ('3517473264', '5493517473264', 'george fabre', 'george', 'georgecfabre8@gmail.com', 'La Rioja 1207, X5000 Córdoba, Argentina', NULL, '20955777833', 'DNI', 422816),
  ('3513601000', '5493513601000', 'matias laquiz', 'matias', 'matiaslaquiz@gmail.com', 'Anacreonte 282, X5001BID Córdoba, Argentina', NULL, '34689104', 'DNI', 421156),
  ('3517872318', '5493517872318', 'Pedro C Mazzuchini', 'Pedro', 'pedromazzu@hotmail.com', 'Domingo de Irala 1082, X5016 Córdoba, Argentina', NULL, '24060234', 'DNI', 421153),
  ('3515070747', '5493515070747', 'Carla Bulacio', 'Carla', 'carlabulacio@hotmail.com', 'De las Celosias 1, X5008 Córdoba, Córdoba, Argentina', NULL, '30970104', 'DNI', 420765),
  ('3512385315', '5493512385315', 'dasol sas', 'dasol', 'dasol@gmail.com', 'Javier Lascano Colodrero 2737, X5008ADB Córdoba, Argentina', '30717402096', NULL, 'CUIT', 420537),
  ('3517515244', '5493517515244', 'carina Mendoza', 'carina', 'aabiimendozaa@gmail.com', 'Cajamarca, X5017 Córdoba, Argentina', NULL, '27275539150', 'DNI', 419701),
  ('3516116671', '5493516116671', 'lorena gallegos', 'lorena', 'lorebgallegos@gmail.com', '3 de Junio, X5012 Córdoba, Argentina', NULL, '27-33893381-4', 'DNI', 419585),
  ('3516593253', '5493516593253', 'Cintia Soledad Duarte', 'Cintia', 'cintiasoledadduarte0@gmail.com', 'Córdoba, X5008 Córdoba, Argentina', NULL, '28432824', 'DNI', 419353),
  ('3517700039', '5493517700039', 'Sergio maximiliano  Julio', 'Sergio', 'maxijulio1717@gmail.com', 'M. Álvarez de las Casas 273, X5001 Córdoba, Argentina', NULL, '36232180', 'DNI', 418933),
  ('3513279191', '5493513279191', 'oscar salva', 'oscar', 'oscarsalva53@hotmail.com', 'Río Negro 5565, X5017 Córdoba, Argentina', NULL, '27275622', 'DNI', 418676),
  ('3515196288', '5493515196288', 'Silvia Vieyra', 'Silvia', 'florenciadominguez19@gmail.com', 'Isabela 2119, X5017 Córdoba, Argentina', NULL, '18503806', 'DNI', 418622),
  ('3515579724', '5493515579724', 'Debora  Bercovich', 'Debora', 'compras.candyland@gmail.com', 'Yapeyú 1713, X5000 Córdoba, Argentina', '27444745105', NULL, 'CUIT', 418445),
  ('3513203626', '5493513203626', 'david marcilli', 'david', 'ventas@marcilli.com.ar', 'Sta Fe 840, X5000 Córdoba, Argentina', NULL, '14894733', 'DNI', 418439),
  ('3512364739', '5493512364739', 'Gustavo Ceballos', 'Gustavo', 'gussceb91@gmail.com', 'Coronel Manuel Namuncurá 5898, X5002 Córdoba, Argentina', NULL, '36140673', 'DNI', 418428),
  ('3513001976', '5493513001976', 'Lucas Carmona', 'Lucas', 'cerropana@hotmail.com', 'Av. Renault Argentina 1912, X5017 Córdoba, Argentina', NULL, '20-32541086-9', 'DNI', 417599),
  ('3541390667', '5493541390667', 'Maximiliano Lema', 'Maximiliano', 'maxijhail@gmail.com', 'P. Carranza 774, X5166 Córdoba, Córdoba, Argentina', '20 35882499 5', NULL, 'CUIT', 417522),
  ('3516617314', '5493516617314', 'Consuelo Avila', 'Consuelo', 'consuavila78@gmail.com', 'Del Cid 113, Villa Allende, Córdoba, Argentina', NULL, '27012660', 'DNI', 417496),
  ('3571327571', '5493571327571', 'Julian Urrutia', 'Julian', 'ujulian094@gmail.com', 'Cmte. Espora 1815, X5850 Río Tercero, Córdoba, Argentina', NULL, '22880763', 'DNI', 417319),
  ('3517352893', '5493517352893', 'Alfredo SAMUDIO ENCINA', 'Alfredo', 'samudioalfre8@gmail.com', 'C. Principal Nuestro Hogar III, Córdoba, Argentina', '27949290558', NULL, 'CUIT', 417241),
  ('1139332396', '5491139332396', 'liliana Argañaraz', 'liliana', 'liliana.noemi79@hotmail.com', 'Colonia 450, B1754 Villa Luzuriaga, Provincia de Buenos Aires, Argentina', NULL, '27155136', 'DNI', 417117),
  ('3513700929', '5493513700929', 'Lucas Gabriel Brunetto', 'Lucas', 'lucasgbrunetto@gmail.com', 'Dr. Antolin Torres 3225, X5016 Córdoba, Argentina', NULL, '38987791', 'DNI', 416955),
  ('3513975442', '5493513975442', 'Guillermo sibilla', 'Guillermo', 'uransonia1@gmail.com', '24 de Septiembre 1290, 5000 Córdoba, Córdoba, Argentina', '20216251254', NULL, 'CUIT', 416608),
  ('3513492782', '5493513492782', 'Giuliana cabrera', 'Giuliana', 'cabreragiuliana.2208@gmail.com', 'Rivera Indarte 1401, X5000JBG Córdoba, Argentina', NULL, '27401056705', 'DNI', 416456),
  ('3516728769', '5493516728769', 'roberto carlos marquez', 'roberto', 'cachubar@hotmail.com', 'José Ingenieros 2315, X5014ACS Córdoba, Argentina', NULL, '25040441', 'DNI', 415488),
  ('3516437551', '5493516437551', 'sofia mariuse', 'sofia', 'sofiamariuse@gmail.com', 'Transito Caceres de Allende, X5000 Córdoba, Argentina', NULL, '38332184', 'DNI', 415476),
  ('3517364541', '5493517364541', 'oriana lopez', 'oriana', 'julianlopez2096@gmail.com', 'Sta Rosa 2533, X5000 Córdoba, Argentina', NULL, '41481338', 'DNI', 415375),
  ('3576446368', '5493576446368', 'Romika37 Romero', 'Romika37', 'romiaarrieta13@gmail.com', 'Independencia, Villa Concepción del Tio, Córdoba, Argentina', NULL, '41034385', 'DNI', 415262),
  ('3541315720', '5493541315720', 'mirta gonzalez', 'mirta', 'mirtagonzalezdv4@gmail.com', 'Gualeguay Icho Cruz, X5153 Villa Icho Cruz, Córdoba, Argentina', NULL, '41828957', 'DNI', 415247),
  ('3512146917', '5493512146917', 'maria isabel miño', 'maria', 'carlosavila47@hotmail.com', 'Entre Ríos 2269, X5006 CCY, Córdoba, Argentina', '27110532542', NULL, 'CUIT', 414881),
  ('3512024271', '5493512024271', 'Martin Funes', 'Martin', 'martingfunes@hotmail.com', 'C. 8, Col. Alvear, Mendoza, Argentina', NULL, '23006920', 'DNI', 414817),
  ('3513792464', '5493513792464', 'Lautaro Peralta', 'Lautaro', 'peraltalautaro696@gmail.com', 'Int. Dr. Juan Carlos Avalos, X5000 Córdoba, Argentina', NULL, '47304231', 'DNI', 414638),
  ('3516378871', '5493516378871', 'Laura Reriani', 'Laura', 'laurajreriani@hotmail.com', 'Av. Vélez Sarsfield 3329, X5016GDE Córdoba, Argentina', '27169473531', NULL, 'CUIT', 414482),
  ('3513241139', '5493513241139', 'nadia cisneros', 'nadia', 'nadiacisnero08@gmail.com', 'Calle 29, Córdoba, Argentina', NULL, '45154436', 'DNI', 414257),
  ('3516837729', '5493516837729', 'franco burgos', 'franco', 'francoburgos736@gmail.com', 'Guasapampa 2892, X5014KOF Córdoba, Argentina', NULL, '28687736', 'DNI', 414205),
  ('3549636311', '5493549636311', 'Diego Zapata', 'Diego', 'diego_zapata13@hotmail.com', 'Av. 25 de Mayo 1389, Villa de Soto, Córdoba, Argentina', NULL, '38410841', 'DNI', 413764),
  ('3516222775', '5493516222775', 'carolina contreras', 'carolina', 'caro020187@gmail.com', 'Dr. Arturo Capdevila 13000, X5012 Córdoba, Argentina', NULL, '27322140849', 'DNI', 413163),
  ('3513347535', '5493513347535', 'luis simbron', 'luis', 'c_seba_06@hotmail.com', 'Ricardo Rojas 130d, X5166 Cosquín, Córdoba, Argentina', NULL, '28853723', 'DNI', 413066),
  ('3512267442', '5493512267442', 'claudio molina', 'claudio', 'galofran@gmail.com', 'Pje. de la Vega, X5808 Río Cuarto, Córdoba, Argentina', NULL, '32458355', 'DNI', 413040),
  ('3541679541', '5493541679541', 'natalia soledad amaya', 'natalia', 'nataliamaya772@gmail.com', 'Roma 1715, X5152 Villa Carlos Paz, Córdoba, Argentina', NULL, '36120105', 'DNI', 412726),
  ('3512886446', '5493512886446', 'wang fengyun3512886446', 'wang', 'wangfengyun1987@gmail.com', 'Blvd. de los Alemanes, Córdoba, Argentina', NULL, '95362700', 'DNI', 412552),
  ('3834295410', '5493834295410', 'Maximiliano Quiroga', 'Maximiliano', 'enet.maximiliano.quiroga@gmail.com', 'Av. Argentina Indigena, K4700 San Fernando del Valle de Catamarca, Catamarca, Argentina', NULL, '49010286', 'DNI', 412396),
  ('3512454928', '5493512454928', 'silvia García', 'silvia', 'koki.garcia.33@gmail.com', 'Pasaje Quinchan 1077, X5002 Córdoba, Argentina', NULL, '27299691123', 'DNI', 412101),
  ('3541589507', '5493541589507', 'Ulises zarates', 'Ulises', 'zaratesulises@gmail.com', 'Asunción 71, X5152 Villa Carlos Paz, Córdoba, Argentina', NULL, '40029685', 'DNI', 412080),
  ('3547506247', '5493547506247', 'Daniela Emilse Sanchez', 'Daniela', 'danielaemilsesanchez@gmail.com', 'Mariquita Sánchez 433, X5850 Río Tercero, Córdoba, Argentina', NULL, '35064010', 'DNI', 412066),
  ('3515524739', '5493515524739', 'diego armando mil alzamora', 'diego', 'mildiego7@gmail.com', 'Av. Colón 2144, X5003CEI Córdoba, Argentina', NULL, '43271492', 'DNI', 411999),
  ('3541570537', '5493541570537', 'Lourdes Patiño', 'Lourdes', 'lourdespatino2017@gmail.com', 'Mayor PM Casado, X5153, Córdoba, Argentina', NULL, '22288691', 'DNI', 411490),
  ('3548608817', '5493548608817', 'macarena bazan', 'macarena', 'bazanmacarena91@gmail.com', 'Córdoba, La Cumbre, Córdoba, Argentina', NULL, '40201818', 'DNI', 411275),
  ('3515406284', '5493515406284', 'Abigail López', 'Abigail', 'abigaildayanalopez95@gmail.com', 'Fiambala, X5006 Córdoba, Argentina', NULL, '38988042', 'DNI', 411137),
  ('3515071880', '5493515071880', 'Victoria Nievas', 'Victoria', 'victorianievas38@gmail.com', 'Arauco 1650, X5010 Córdoba, Argentina', NULL, '38409001', 'DNI', 411105),
  ('3516132664', '5493516132664', 'claudia luna', 'claudia', 'clauuubelu_@hotmail.es', 'Publica F 4645 Publica F 4645, X5017 Córdoba, Córdoba, Argentina', NULL, '23783484', 'DNI', 411102),
  ('3544467120', '5493544467120', 'Ignacio Perez', 'Ignacio', 'pignacio781@gmail.com', 'Villa Dolores, X5017 Córdoba, Argentina', NULL, '32483719', 'DNI', 411080),
  ('3517637324', '5493517637324', 'Graciela osses', 'Graciela', 'gracielamazzaforte@gmail.com', 'Argandoña 4919, X5006 Córdoba, Argentina', NULL, '27207852746', 'DNI', 411027),
  ('3516229909', '5493516229909', 'ema salce', 'ema', 'emagta@gmail.com', 'Carcaraña 1789, Villa Allende, Córdoba, Argentina', NULL, '32338974', 'DNI', 410991),
  ('3515171583', '5493515171583', 'azul roldan', 'azul', 'azulroldan49@gmail.com', 'Conrado Nale Roxlo 788, X5001 Córdoba, Argentina', NULL, '49556265', 'DNI', 410989),
  ('3513961271', '5493513961271', 'Cirene Casas', 'Cirene', 'cire2333@gmail.com', 'Av. Armada Argentina 259, X5016DFC Córdoba, Argentina', NULL, '35529516', 'DNI', 410924),
  ('3757606240', '5493757606240', 'Evelyn Prence', 'Evelyn', 'evelynprence456@gmail.com', 'Rastreador Fournier 370, X5850 Río Tercero, Córdoba, Argentina', NULL, '44528997', 'DNI', 410908),
  ('3517657917', '5493517657917', 'va Ferreyra', 'va', 'vferreyra0783@gmail.com', 'Av. Patria 1025, X5022 Córdoba, Argentina', NULL, '30005077', 'DNI', 410899),
  ('3521535210', '5493521535210', 'marisa del valle oliva', 'marisa', 'marisadelvalleoliva@gmail.com', 'Guido Spano 158, X5200 Dean Funes, Córdoba, Argentina', NULL, '27277168672', 'DNI', 410769),
  ('3541227115', '5493541227115', 'Fiorela Andrade', 'Fiorela', 'fiorelaandrade1997@gmail.com', 'Lavalle, Córdoba, Argentina', NULL, '40502911', 'DNI', 410745),
  ('3571638277', '5493571638277', 'romina Jimenez', 'romina', 'jimenezromina657@gmail.comj', 'Cno Colonia Tirolesa, Córdoba, Argentina', NULL, '38417803', 'DNI', 410557),
  ('3543303088', '5493543303088', 'Florencia Marín', 'Florencia', 'florcitha_m@hotmail.com', 'Pozo de la Loma 8660, X5022 Córdoba, Argentina', NULL, '39173885', 'DNI', 410457),
  ('3826405219', '5493826405219', 'Ebe Moreno', 'Ebe', 'ebemoreno75@gmail.com', 'Rioja, Santa Rita de Catuña, La Rioja, Argentina', NULL, '39904137', 'DNI', 410314),
  ('3512196829', '5493512196829', 'jonathan baracat', 'jonathan', 'baracatjoeljonathan@gmail.com', 'Nispo 1528, X5017 Córdoba, Argentina', NULL, '20363563733', 'DNI', 410307),
  ('3541271082', '5493541271082', 'brenda avila', 'brenda', 'breenavila00@icloud.com', 'Av. San Martin 3085, X5165 Santa María de Punilla, Córdoba, Argentina', NULL, '41964253', 'DNI', 410282),
  ('3513050806', '5493513050806', 'Jose maria puig jose', 'Jose', 'jozepuig@gmail.com', 'Ituzaingó 1202, X5000IJZ Córdoba, Argentina', NULL, '32158186', 'DNI', 410191),
  ('3515407914', '5493515407914', 'paloma cabanillas', 'paloma', 'cabanillasprietopaloma@gmail.com', 'Córdoba, X5113, Córdoba, Argentina', NULL, '44192645', 'DNI', 410147),
  ('3518090510', '5493518090510', 'maricel Elizabeth gonzalez', 'maricel', 'mg7884554@gmail.com', 'Patricias Argentinas 150, X5101 Yocsina, Córdoba, Argentina', NULL, '35667761', 'DNI', 409993),
  ('3516986626', '5493516986626', 'María Laura Lopez', 'María', 'marilau_22_17@hotmail.com', 'Luis Ángel Firpo 2074, X5008 Córdoba, Argentina', NULL, '33117222', 'DNI', 409972),
  ('1151058555', '5491151058555', 'macarena dardik', 'macarena', 'macadardik@gmail.com', '24 de Noviembre 1966, C1242AAO Cdad. Autónoma de Buenos Aires, Argentina', NULL, '46441436', 'DNI', 409914),
  ('3517558537', '5493517558537', 'evelyn sagen', 'evelyn', 'eveesagen@hotmail.com.ar', 'Martín García 712, X5008 Córdoba, Argentina', NULL, '37315570', 'DNI', 409869),
  ('3516576214', '5493516576214', 'ariel heredia', 'ariel', 'arielheredia80@gmail.com', 'Ferroviarios 1407, X5000 Córdoba, Argentina', NULL, '32786186', 'DNI', 409786),
  ('3516544482', '5493516544482', 'Gaston peralta', 'Gaston', 'lugaston0987@gmail.com', 'reconquista 1142, X5151 La Calera, Córdoba, Argentina', NULL, '33635525', 'DNI', 409294),
  ('3512644672', '5493512644672', 'jonathan del valle', 'jonathan', 'jonidel16@gmail.com', 'Sarmiento 285, X5151 La Calera, Córdoba, Argentina', NULL, '41640768', 'DNI', 409273),
  ('3513676266', '5493513676266', 'Leo chen', 'Leo', 'leochenyong@gmail.com', 'Blvd. Cangallo 2961, X5123 Córdoba, Argentina', '20956371423', NULL, 'CUIT', 409166),
  ('3516525798', '5493516525798', 'gabriel salas', 'gabriel', 'gabisalas063@gmail.com', 'Maestro Vidal 1404, X5010 Córdoba, Argentina', NULL, '38.107.063', 'DNI', 409081),
  ('3513902161', '5493513902161', 'Belen Dominguez', 'Belen', 'belend618@gmail.com', '27 de Abril 1968, X5002AAH Córdoba, Argentina', NULL, '39693442', 'DNI', 408617),
  ('3541397682', '5493541397682', 'karen Yuliana manzanelli', 'karen', 'karenmanzanelli04@gmail.com', 'Valle Escondido 121, X5152 Villa Carlos Paz, Córdoba, Argentina', NULL, '38885989', 'DNI', 408555),
  ('3564507250', '5493564507250', 'Andrea pereyra', 'Andrea', 'andreapereyra75@gmail.com', 'Av. Eva Perón, U9100 Trelew, Chubut, Argentina', NULL, '28657222', 'DNI', 408332),
  ('3515433026', '5493515433026', 'Alejandra Tejeda', 'Alejandra', 'aletej@hotmail.com', 'Wenceslao Escalante 386, X5016 Córdoba, Argentina', '27250681068', NULL, 'CUIT', 408122),
  ('3541740927', '5493541740927', 'antonella daiana quevedoo', 'antonella', 'la-antoo@live.com.ar', 'Bolivia 1100, X5152 Villa Carlos Paz, Córdoba, Argentina', NULL, '27406804270', 'DNI', 407525),
  ('3512096671', '5493512096671', 'Jeremias Esteban', 'Jeremias', 'jereeesteban@gmail.com', 'Ramon Eduardo Anchoris 5382, X5012 Córdoba, Argentina', NULL, '45084361', 'DNI', 407500),
  ('3517016336', '5493517016336', 'Silvana Cristina Chavez', 'Silvana', 'erciliamargamoreno@gmail.com', 'Juan del Campillo 106, X5001 Córdoba, Argentina', '27213911290', NULL, 'CUIT', 407485),
  ('1132991263', '5491132991263', 'Victor Abriatta', 'Victor', 'victor.abriatta@gmail.com', 'Charcas 2452, X5000 Córdoba, Argentina', NULL, '20948146', 'DNI', 407394),
  ('3525582423', '5493525582423', 'emilce llanos', 'emilce', 'llanosemilce2423@gmail.com', 'C. Pedro Patat Sur 302, X5223 Col. Caroya, Córdoba, Argentina', NULL, '27300099910', 'DNI', 406970),
  ('3512571339', '5493512571339', 'Cristian cortez', 'Cristian', 'cortezcristian1905@gmail.com', 'Tte. Héctor Volponi, Malvinas Argentinas, Córdoba, Argentina', NULL, '41032739', 'DNI', 406808),
  ('3516113291', '5493516113291', 'flor damico', 'flor', 'flordamico1@gmail.com', 'Cnel. Pedro Zanni 365, X5003GQA Córdoba, Argentina', NULL, '39080199', 'DNI', 406786),
  ('3515918476', '5493515918476', 'francisco actis', 'francisco', 'fran.actis06@gmail.com', 'Baradero 2021, X5014 Córdoba, Argentina', NULL, '35089894', 'DNI', 406677),
  ('3518198147', '5493518198147', 'Josefina Zelis Garzon', 'Josefina', 'josefinazelisgarzon@gmail.com', 'Av. Hipólito Yrigoyen, X5000 Córdoba, Argentina', NULL, '45086705', 'DNI', 406098),
  ('3513983639', '5493513983639', 'Tania espindola', 'Tania', 'taniaespindola222@gmail.com', 'Calingasta, Córdoba, Argentina', NULL, '38187581', 'DNI', 404754),
  ('3516201783', '5493516201783', 'Julio porcel', 'Julio', 'delalcazarlhasas@gmail.com', 'Cnel. Pedro Zanni 992, X5003 Córdoba, Argentina', NULL, '2020873475', 'DNI', 404407),
  ('3516710300', '5493516710300', 'Agustin Escobal', 'Agustin', 'escobalagustin@gmail.com', 'E. Bodereau 8700, X5018 Córdoba, Argentina', NULL, '33892165', 'DNI', 403397),
  ('3517551663', '5493517551663', 'Maria Ximena Paira', 'Maria', 'xpaira@gmail.com', 'Cochabamba 1693, X5000 Córdoba, Argentina', '27324073804', NULL, 'CUIT', 402978),
  ('3516223464', '5493516223464', 'lucas dameto', 'lucas', 'lucas8matias4@gmail.com', 'Av. Alfonsina Storni 793, X5019 Córdoba, Argentina', NULL, '30967993', 'DNI', 402975),
  ('3518626800', '5493518626800', 'Marcos Auchterlonie', 'Marcos', 'marcosauchterlonie@gmail.com', 'José Roque Funes 1253, X5009LFG Córdoba, Argentina', NULL, '36984036', 'DNI', 402807),
  ('3512835040', '5493512835040', 'Valentina Torres', 'Valentina', 'valentina.1.torres60@gmail.com', 'C. Pública 3, Córdoba, Argentina', NULL, '43997001', 'DNI', 402356),
  ('3513181621', '5493513181621', 'Mariano Miles', 'Mariano', 'mariano@aceleradoradeventas.com', 'Damian Garat 2736, X5008AHO Córdoba, Argentina', NULL, '25609993', 'DNI', 402271),
  ('3515205631', '5493515205631', 'hugo muttigliengo', 'hugo', 'muttigliengohugo@yahoo.com.ar', 'Av. Fernando Fader 3637, X5009 Córdoba, Argentina', NULL, '25489871', 'DNI', 402251),
  ('3513980188', '5493513980188', 'giannina fredi', 'giannina', 'gianninafredi@gmail.com', 'Diego de Loria Carrasco 2053, X5012 Córdoba, Argentina', NULL, '36125407', 'DNI', 401977),
  ('3547661769', '5493547661769', 'catalina Falabella', 'catalina', 'catalinafalabellas@gmail.com', 'Sarmiento, X5186 Alta Gracia, Córdoba, Argentina', NULL, '40974313', 'DNI', 401277),
  ('3456431833', '5493456431833', 'Briana Perricone', 'Briana', 'briisperricone@gmail.com', 'Dr. Santillan, X5186 Alta Gracia, Córdoba, Argentina', NULL, '52153156', 'DNI', 401274),
  ('3512298117', '5493512298117', 'leandro Baligan', 'leandro', 'baligan.leandro@gmail.com', 'Barcelona, X5000 Córdoba, Argentina', NULL, '34486563', 'DNI', 396528),
  ('3512341591', '5493512341591', 'Gabriel Vera', 'Gabriel', 'abastecimientovera@gmail.com', 'Avenida Padre Antonio María Claret 6125, X5147 Córdoba, Córdoba, Argentina', '20268156187', NULL, 'CUIT', 396497),
  ('3512516888', '5493512516888', 'lucas zheng', 'lucas', 'supermercadosuco@gmail.com', 'Mariano Boedo 1951, X5006EGU X5006EGU Córdoba, Argentina', NULL, '95342027', 'DNI', 396250),
  ('3515337263', '5493515337263', 'gaby sacramenti', 'gaby', 'bauca0021@gmail.com', 'Julio A. Roca, X5000 Córdoba, Argentina', NULL, '94343268', 'DNI', 394094),
  ('3516819768', '5493516819768', 'jose luis Loyola', 'jose', 'josesonidoeiluminacion123@gmail.com', 'Lola Membrives, X5001 Córdoba, Argentina', NULL, '41594177', 'DNI', 390314),
  ('1161837961', '5491161837961', 'martin silverio', 'martin', 'martinsilverio@hotmail.com.ar', 'Av. Amancio Alcorta 2850, C1437 Cdad. Autónoma de Buenos Aires, Argentina', NULL, '32951122', 'DNI', 382459),
  ('3541559213', '5493541559213', 'Noe Tapia', 'Noe', 'alejososmivida192@gmail.com', 'Bv. Sarmiento 325, X5152 Villa Carlos Paz, Córdoba, Argentina', NULL, '32467125', 'DNI', 377731),
  ('3512485269', '5493512485269', 'Melissa Lin', 'Melissa', 'linjuanyun2019@gmail.com', 'Av. Nuevo Mundo 1373, X5001 Córdoba, Argentina', NULL, '94556307', 'DNI', 371399),
  ('3571354822', '5493571354822', 'Eugenia Torres', 'Eugenia', 'eugekader16@gmail.com', 'Río Colorado 1071, X5850 Río Tercero, Córdoba, Argentina', NULL, '41034953', 'DNI', 371380),
  ('2494546036', '5492494546036', 'maria zubeldia', 'maria', 'maruzubeldia02@gmail.com', 'Maipú 721, B7000 Tandil, Provincia de Buenos Aires, Argentina', NULL, '42491692', 'DNI', 353798),
  ('3548599098', '5493548599098', 'Jose eduardo Tassone', 'Jose', 'eduardotassone@hotmail.com', 'Sarmiento 38, X5184BMB Capilla del Monte, Córdoba, Argentina', '23177944149', NULL, 'CUIT', 346164),
  ('3782436407', '5493782436407', 'Maria jose haro', 'Maria', 'majomonzonharo1975@gmail.com', 'Sta Cruz 1510, W3410 Corrientes, Argentina', NULL, '27271893871', 'DNI', 335956),
  ('3513172301', '5493513172301', 'celeste villan', 'celeste', NULL, 'Avenida Cornelio Saavedra 1657, X5008 Córdoba, Córdoba, Argentina', NULL, '35525575', 'DNI', 301644),
  ('3513520417', '5493513520417', 'Mauro santillan', 'Mauro', NULL, 'Calixto Gauna 1060, X5010 Córdoba, Argentina', NULL, '42051666', 'DNI', 286820),
  ('3517517678', '5493517517678', 'juan Drincovich', 'juan', 'juandrincovich@live.com.ar', 'Tte. Gral. Donato Alvarez 9776, X5022IHQ Córdoba, Argentina', NULL, '28655162', 'DNI', 238183),
  ('3516290260', '5493516290260', 'Fausto cabrera cabrera', 'Fausto', 'cabrerafausto276@gmail.com', 'Av. Colón 3095, X5003 DDB, Córdoba, Argentina', NULL, '43925519', 'DNI', 225101),
  ('3517138125', '5493517138125', 'manuel valverde', 'manuel', 'escobarvalverde@hotmail.com', 'Congreso 550, X5017 Córdoba, Argentina', NULL, '26393498', 'DNI', 200667),
  ('3513493902', '5493513493902', 'veronica rosas', 'veronica', 'verorosas02@hotmail.com', 'Homero 2457, X5012 Córdoba, Argentina', NULL, '28428192', 'DNI', 195003),
  ('3515097598', '5493515097598', 'sikvia migueli', 'sikvia', 'miguelosilvia@gmail.com', 'Dr. Arturo Capdevila 1672, X5012 Córdoba, Argentina', NULL, '23897653', 'DNI', 190281),
  ('3512749711', '5493512749711', 'natalia heredia', 'natalia', 'nataliasoledadheredia@gmail.com', 'Av. Renault Argentina, X5017 Córdoba, Argentina', NULL, '30843728', 'DNI', 180058),
  ('3516742204', '5493516742204', 'Luisa Roman', 'Luisa', 'tayautoservicio@gmail.com', 'Maestro Vidal 939, X5000 Córdoba, Argentina', '23251793484', NULL, 'CUIT', 177232),
  ('3541673954', '5493541673954', 'Andrés Sebastián Migoya', 'Andrés', 'migoyandy@gmail.com', 'Avenida San Martín 772, X5152 Villa Carlos Paz, Córdoba, Argentina', '20286574543', NULL, 'CUIT', 26209)
),
excel AS (
  SELECT
    suffix10, phone_canon, nombre, nombre_de_pila, email, direccion, cuit,
    jsonb_strip_nulls(jsonb_build_object(
      'origen', 'ecommerce_centralo',
      'codigo_centralo', codigo_centralo,
      'tipo_documento', tipo_doc,
      'dni', dni,
      'cuit', cuit
    )) AS datos_personales,
    jsonb_build_object(
      'origen', 'ecommerce_centralo',
      'codigo_centralo', codigo_centralo,
      'import', 'altas-ecommerce-2026-09-12',
      'excel', 'Users-2026-04-24'
    ) AS metadata,
    codigo_centralo
  FROM excel_raw
),
existing AS (
  SELECT
    e.suffix10,
    c.id AS client_id,
    c.phone_number,
    c.codigo,
    row_number() OVER (
      PARTITION BY e.suffix10
      ORDER BY
        (
          lower(COALESCE(c.nombre, '') || ' ' || COALESCE(c.razon_social, ''))
          LIKE '%' || lower(split_part(e.nombre, ' ', 1)) || '%'
        ) DESC,
        (c.phone_number ~ '^549[1-9]') DESC,
        (c.codigo IS NOT NULL) DESC,
        c.id
    ) AS rn
  FROM excel e
  JOIN del_corro.clients c
    ON right(regexp_replace(COALESCE(c.phone_number, ''), '[^0-9]', '', 'g'), 10) = e.suffix10
   AND c.phone_number NOT LIKE 'dup-merged-%'
),
keepers AS (
  SELECT suffix10, client_id FROM existing WHERE rn = 1
),
to_insert AS (
  SELECT e.*
  FROM excel e
  LEFT JOIN keepers k ON k.suffix10 = e.suffix10
  WHERE k.client_id IS NULL
),
ins_clients AS (
  INSERT INTO del_corro.clients (
    phone_number, nombre, razon_social, nombre_de_pila,
    lista_precios_id, codigo, activo_ai, email, cuit,
    etiqueta, is_primary, whatsapp_estado, is_mock,
    datos_personales, metadata
  )
  SELECT
    t.phone_canon,
    t.nombre,
    t.nombre,
    t.nombre_de_pila,
    1,
    NULL,
    true,
    t.email,
    t.cuit,
    'CLIENTES_WEB',
    true,
    'no_validado'::core.whatsapp_estado_cliente_enum,
    false,
    t.datos_personales,
    t.metadata
  FROM to_insert t
  ON CONFLICT (phone_number) DO NOTHING
  RETURNING id, phone_number
),
ins_loc AS (
  INSERT INTO del_corro.client_locations (
    client_id, address_text, is_primary, source, geocode_status, created_by
  )
  SELECT ic.id, t.direccion, true, 'ecommerce_centralo', 'pending', 'altas-ecommerce-2026-09-12'
  FROM ins_clients ic
  JOIN to_insert t ON t.phone_canon = ic.phone_number
  WHERE t.direccion IS NOT NULL
  RETURNING client_id
),
to_migrate AS (
  SELECT
    c.id,
    c.razon_social,
    c.codigo,
    c.lista_precios_id,
    c.dia_de_visita,
    c.dia_de_entrega,
    c.cuit,
    t.direccion,
    c.email,
    c.vendedor,
    c.activo_ai,
    row_number() OVER (ORDER BY c.id) AS rn
  FROM del_corro.clients c
  JOIN ins_clients ic ON ic.id = c.id
  JOIN to_insert t ON t.phone_canon = ic.phone_number
  WHERE c.pdv_id IS NULL
),
inserted_pdv AS (
  INSERT INTO del_corro.puntos_venta (
    razon_social, codigo, lista_precios_id,
    dia_de_visita, dia_de_entrega,
    cuit, direccion, email, vendedor, activo_ai
  )
  SELECT
    tm.razon_social, tm.codigo, tm.lista_precios_id,
    tm.dia_de_visita, tm.dia_de_entrega,
    tm.cuit, tm.direccion, tm.email, tm.vendedor, tm.activo_ai
  FROM to_migrate tm
  ORDER BY tm.rn
  RETURNING id
),
numbered_pdv AS (
  SELECT id, row_number() OVER (ORDER BY id) AS rn FROM inserted_pdv
),
paired AS (
  SELECT tm.id AS client_id, np.id AS pdv_id
  FROM to_migrate tm
  JOIN numbered_pdv np ON np.rn = tm.rn
),
upd_pdv AS (
  UPDATE del_corro.clients c
  SET pdv_id = p.pdv_id, updated_at = now()
  FROM paired p
  WHERE c.id = p.client_id
  RETURNING c.id
),
ensured_etiqueta AS (
  INSERT INTO del_corro.etiquetas (name, parent_id, is_starred)
  SELECT 'Clientes Web', NULL, true
  WHERE NOT EXISTS (
    SELECT 1 FROM del_corro.etiquetas WHERE name = 'Clientes Web'
  )
  RETURNING id
),
etiqueta AS (
  SELECT id FROM ensured_etiqueta
  UNION ALL
  SELECT id FROM del_corro.etiquetas WHERE name = 'Clientes Web'
  LIMIT 1
),
all_targets AS (
  SELECT client_id FROM keepers
  UNION
  SELECT id FROM ins_clients
),
ins_tags AS (
  INSERT INTO del_corro.clientes_etiquetas (client_id, etiqueta_id)
  SELECT t.client_id, e.id
  FROM all_targets t
  CROSS JOIN etiqueta e
  ON CONFLICT DO NOTHING
  RETURNING client_id
),
ensured_grupo AS (
  INSERT INTO del_corro.grupos (nombre, etiqueta_ids, activo_ai)
  SELECT 'Clientes Web e-commerce', ARRAY[e.id], true
  FROM etiqueta e
  WHERE NOT EXISTS (
    SELECT 1 FROM del_corro.grupos WHERE nombre = 'Clientes Web e-commerce'
  )
  RETURNING id
),
grupo AS (
  SELECT id FROM ensured_grupo
  UNION ALL
  SELECT id FROM del_corro.grupos WHERE nombre = 'Clientes Web e-commerce'
  LIMIT 1
),
ins_agenda AS (
  INSERT INTO del_corro.agenda (
    grupo_id, meta_plantilla_id, tipo, hora_envio, fecha_programada,
    activo, origen
  )
  SELECT
    g.id,
    '384f5f6f-74a1-4d46-aa00-b9af2d76af35'::uuid,
    'puntual',
    TIME '11:30',
    DATE '2026-09-12',
    true,
    'ecommerce_welcome'
  FROM grupo g
  WHERE NOT EXISTS (
    SELECT 1
    FROM del_corro.agenda a
    WHERE a.origen = 'ecommerce_welcome'
      AND a.fecha_programada = DATE '2026-09-12'
      AND a.meta_plantilla_id = '384f5f6f-74a1-4d46-aa00-b9af2d76af35'::uuid
  )
  RETURNING id
)
SELECT json_build_object(
  'excel_unicos', (SELECT COUNT(*) FROM excel),
  'existentes_tagged', (SELECT COUNT(*) FROM keepers),
  'insertados', (SELECT COUNT(*) FROM ins_clients),
  'locations', (SELECT COUNT(*) FROM ins_loc),
  'pdvs', (SELECT COUNT(*) FROM inserted_pdv),
  'tags', (SELECT COUNT(*) FROM ins_tags),
  'etiqueta_id', (SELECT id FROM etiqueta),
  'grupo_id', (SELECT id FROM grupo),
  'agenda_id', (SELECT id FROM ins_agenda)
) AS resultado;
