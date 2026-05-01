# Changelog

All notable changes to DataVisSUS TXT2SQL Agent.

## [0.3.0] - 2026-04-26

### Chores

- Snapshot current multi-query work ([`67f6603`](67f6603652d3a0a8b95e9020e52c0815e92fd103))

### Features

- Add refactored SQL agent with LangGraph ([`33c5a7e`](33c5a7e7a196487d4f01b11b1139a036e66dd4f1))
- Harden multi-query planning and verification ([`9c7cce4`](9c7cce482b8a7c527f25a9469c77f1593603bd3d))

### Other

- **other:** Update project ([`7bb8ff4`](7bb8ff45b4cb67e237c41ba0b235c55997e22040))
- **other:** Update project ([`151b88c`](151b88cb2ac1be6aa344171055a7aec03a818af0))
- **other:** Add script to manager log size ([`5a49a91`](5a49a91c059981ee055d7207eef34f4220423369))
- **other:** Update project ([`380495a`](380495ad82d8d54bec0961d5d7104d79fa76c6ac))
- **other:** Update gitignore ([`6fdb51c`](6fdb51cd82be92cc53fdf5ba1385140fd8d93789))
- **other:** Update project ([`6619dd9`](6619dd9edde81aa010bedf2b468127e294a4aba3))
- **other:** Update project ([`6815641`](681564197a27d56418080a8c7ca46a5272d8e1b1))
- **other:** Update project ([`6a1fe36`](6a1fe3615d058b9f871386bc5a6579ff11047a7e))
- **other:** Merge pull request #1 from MaiconKevyn/develop_interface

Develop interface ([`415cbd2`](415cbd2465d8e6683a67ee12580deb403e8eccd8))
- **other:** Add cid table ([`b4573b1`](b4573b13a6897748b8835f3086b5fbfcffa564f2))
- **other:** Merge pull request #2 from MaiconKevyn/develop_interface

add cid table ([`054d56e`](054d56ed3b1c2102477acc1e4057ab7293dadb7f))
- **other:** Add data handler ([`21eae8a`](21eae8a8b7039b30ea4681a55b023ff0b2ff4609))
- **other:** Remove .idea and __pycache__ directories from git tracking

- Removed PyCharm IDE configuration files (.idea/)
- Removed Python cache files (__pycache__/)
- Updated .gitignore to prevent future tracking

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`a410118`](a41011883d60acf1b5f51d3851d7940ee64b4dae))
- **other:** Remove all __pycache__ directories from git tracking

- Removed Python cache files from src/ and subdirectories
- Cleaned up all __pycache__ directories that were tracked
- Deleted local __pycache__ directories to prevent future issues

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`5465f5d`](5465f5da1dbf59826860c6164469bcede6002465))
- **other:** Update CLAUDE.md with intelligent query routing system

- Add comprehensive documentation for new QueryClassificationService
- Update architecture overview with 10 specialized services
- Add detailed explanation of query routing functionality
- Include Mermaid flow diagram showing routing logic
- Document dual-route system (conversational vs database)
- Add practical usage examples with routing indicators
- Update system flow with Step 3: Intelligent Query Classification
- Document performance benefits and classification accuracy
- Include routing confidence thresholds and visual indicators

Major Features Added:
- 🎯 Intelligent query type detection (DATABASE_QUERY vs CONVERSATIONAL_QUERY)
- 💬 Direct conversational responses for explanatory questions
- 🔍 Traditional SQL pipeline for statistical queries
- 📊 Visual routing indicators in user interface
- ⚡ Performance optimization (3s vs 20-30s response times)

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`cb828ba`](cb828bae662ee273fea3389160fd0313bf7325a3))
- **other:** Implement intelligent query routing system

Complete implementation of query classification and routing functionality:

NEW SERVICES:
- QueryClassificationService: Pattern matching + LLM-based query classification
- Enhanced ConversationalResponseService: Direct conversational processing
- Updated SUSPromptTemplateService: Added DIRECT_CONVERSATIONAL template

ROUTING LOGIC:
- DATABASE_QUERY: Routes to SQL processing pipeline
- CONVERSATIONAL_QUERY: Routes to direct conversational response
- AMBIGUOUS_QUERY: Falls back to database route with lower confidence

ENHANCED COMPONENTS:
- Text2SQLOrchestrator: Integrated routing decision logic
- UserInterfaceService: Visual routing indicators and confidence display
- DependencyContainer: Query classification service integration

TESTING:
- test_routing_integration.py: Comprehensive integration tests (100% accuracy)
- test_interactive_demo.py: Interactive demonstration script

FEATURES:
✅ Pattern-based classification with regex patterns
✅ LLM-based intent detection for ambiguous cases
✅ Confidence scoring and threshold validation
✅ SUS domain-specific classification rules
✅ Visual feedback with routing indicators
✅ Performance optimization (3s vs 20-30s response times)
✅ Fallback mechanisms for classification failures
✅ Comprehensive error handling and recovery

PERFORMANCE RESULTS:
- Classification accuracy: 100% in tests
- Conversational route: ~3s average response time
- Database route: ~20-30s average response time
- Routing confidence: 0.80-0.90 typical range

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`9a5af52`](9a5af5238b733a25eb203795faf95af0a78d8966))
- **other:** Update project ([`513b95a`](513b95a33e81a09398684e5aebd15ce3b8c9ecd7))
- **other:** Update project ([`53d4508`](53d4508aabac98c92e6034d94fe2d762787e1827))
- **other:** Merge pull request #3 from MaiconKevyn/chat_history

Chat history ([`11146d0`](11146d0830c0ac1528dca7cf2afffce4f1d747fa))
- **other:** Update plann ([`d1270b2`](d1270b26a071d33046790044cad8301a67dbbf38))
- **other:** Update ([`9d7e1dc`](9d7e1dcd39e1735f592257a8550375098052d795))
- **other:** Update project ([`ec23462`](ec2346215df73bd68b92abc3b64a1d02774763d5))
- **other:** Update project ([`5d67a0d`](5d67a0d1490b7951082c4d0ba850df9382131483))
- **other:** Merge pull request #4 from MaiconKevyn/multiagent_architecture

Multiagent architecture ([`981c8f6`](981c8f6b4712417a947c666e07bb2a76fd1438dc))
- **other:** Update project ([`f812386`](f8123864b0177018838ec7e8708ff93faf6dac9a))
- **other:** Update frontend ([`e15484b`](e15484b33e7a04c556ece5c38df9ccf1a45c06b5))
- **other:** Update llm conversasional prompt ([`a2ff72a`](a2ff72afb3d959401a5625b81df6947f25772a3d))
- **other:** Merge pull request #5 from MaiconKevyn/multiagent_architecture

Multiagent architecture ([`931b33b`](931b33b5473e2513bea0c540721ae88882e7cdcd))
- **other:** Deleted old tests ([`d541924`](d5419242020acef8dbdb13dfcfc08504f4deaf79))
- **other:** Merge pull request #6 from MaiconKevyn/multiagent_architecture

deleted old tests ([`dedcadf`](dedcadf0cb676cf049bb4b2ea1483e34f3d9108f))
- **other:** Update readme ([`e6e750d`](e6e750dd43ee2313808d369637f9799fb5baaa8b))
- **other:** Update readme ([`542c24b`](542c24b65ba12458a7e2c0b935d5f76f62877dc6))
- **other:** Delete old file ([`5dafefc`](5dafefc1b34704d4894ed8268da93dac63d669d6))
- **other:** Update ground truth ([`d0d74b7`](d0d74b7469dd01983b58b114dea113a2d891d0c1))
- **other:** Update conversational responde ([`3edb3e6`](3edb3e68c4835a064f21e36142310c60df89fb61))
- **other:** Update database ([`fc62044`](fc62044531b71b4348117c3e15999cae0f448f01))
- **other:** Update services ([`e376763`](e37676342d3b175d828eacbd0c3356f2ed9ca33d))
- **other:** Add table service ([`e5c118f`](e5c118f7aebe4f05b8bc27b8d579a63ecc8413bc))
- **other:** Update evaluation scripts ([`394d17a`](394d17ab7d42d67ddfdcff22f8d61cc40c729914))
- **other:** Update project structure ([`b3f2e2e`](b3f2e2e7cd806280ff77c2839f5e08d927d6c363))
- **other:** Update results ([`de014fc`](de014fccedd8d813a9efb00002104afad7ee2cae))
- **other:** Update project ([`3fdf912`](3fdf91244d67f698e39dabec6c936da543b0e55a))
- **other:** Update project ([`6077ad6`](6077ad6a75304e62b1553f7ad506df8563480441))
- **other:** Update project ([`d88c08f`](d88c08f687310a8d8a119c0991800f6f72b4520e))
- **other:** Remove legacy agent ([`1f9d3df`](1f9d3df49df4748b99749b7d823604ea6503c88a))
- **other:** Debug mode and cli agent ([`b3426dd`](b3426dd873b9b0b81f11abd4531daeee9083a45b))
- **other:** Remove CLAUDE.md from repository

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`0d11f96`](0d11f96493f8af1723c2bb3a312ad8f44439671d))
- **other:** Remove obsolete database_setup.py for SQLite

- Remove database_setup.py as LangGraph V3 uses PostgreSQL
- Update error message to reference PostgreSQL instead of SQLite setup

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com> ([`ce073e9`](ce073e92ee03a463cc45a38146cd8720cface7ae))
- **other:** Update gitignore ([`6fbfd84`](6fbfd84b1595ec429ade5c71f731093809a44c95))
- **other:** Update table selection node ([`d98971c`](d98971c6e330b35544ddf14fb0fa0f29adaf1f0b))
- **other:** Update tools ([`1564544`](15645449fba88513a93c056a5467e0330d61381b))
- **other:** Add evaluation selected tables ([`7330164`](7330164e16f0b100609e97c1bd217ca2444355b1))
- **other:** Add prompt template for all tables ([`a084c6f`](a084c6f9709b2d4925bfd092c76fe4932a938cb8))
- **other:** Update project ([`0d7d119`](0d7d1190a3c01fd4700e94c76b8ece29ec2fb81a))
- **other:** Update gitignore ([`c4ff75d`](c4ff75d80b2ee38bc0d05175b457930a9c13503d))
- **other:** Update project ([`057d8e2`](057d8e26e8de6152c6aa485167e69cadb7368f01))
- **other:** Update project ([`1a6b078`](1a6b078091390e698d18d38f41e38e270f43268c))
- **other:** Clean structure ([`d21ce1f`](d21ce1fab575b1b473220c3e4fffcbd20b416dc0))
- **other:** Update project structure ([`b4d1e36`](b4d1e36fd55ff3c2ab03112d38a974a7b2b2285b))
- **other:** Update gitignore ([`64cbf83`](64cbf8302de7a03724e1f4d6f23ccc5c035af133))
- **other:** Update project ([`e777427`](e777427508bdfaf62370a9bcee3c4bf48b835b80))
- **other:** Update project ([`127f93c`](127f93c2392683910ccd6ccf7a90c0cb27b4792e))
- **other:** Update requirements ([`ee2ccd2`](ee2ccd2d38c59cf71e5a888f474c715379e4a92f))
- **other:** Update project ([`e3f2869`](e3f2869ee63bf43b1f2e6ea67cbc941988a68ae2))
- **other:** Update project ([`15b8c36`](15b8c36d36287a77ab9b6fb5430028a6b2a2ae62))
- **other:** Update project ([`5bb80cc`](5bb80ccf2dcf92a06cd09598992fb67dac388710))
- **other:** Update readme ([`8bad5b1`](8bad5b1f5bbbca0931b9819efa0a635a80b90149))
- **other:** Update readme ([`54b6bde`](54b6bde07e89159d5f74b6de3ca8ffe5e0fb2bc1))
- **other:** Update project ([`18e65bc`](18e65bca9b3b8af391dabfb83f7112f682fc3d6f))
- **other:** Remove env ([`186f000`](186f00097fa64027013e119a714d4771a4bccf62))
- **other:** Update cli interactive ([`37e8dfd`](37e8dfd1078f80211115bbea95f015757595c0d7))
- **other:** Update logs and add unit tests ([`81ff54b`](81ff54bf830e9e6a52dbc3cd9e375b47df454964))
- **other:** Update project ([`7058697`](70586976c404694467afb6a611503d6ca89059b6))
- **other:** Update README ([`4cc6440`](4cc6440c961c3023123964fc8ded7956a62bd7f4))
- **other:** Update project ([`27fc4b9`](27fc4b94812a84b2c3418450cc1dee53bcfcc1f8))
- **other:** Update readme ([`decc3f2`](decc3f218660c58bca224b5822de8f8dc6288af3))
- **other:** Update ([`a8e4323`](a8e4323f0e22ae64fa43c329d1b259dae5dec4bf))
- **other:** Remove memory ([`7548c3a`](7548c3a2eec1d4d725b7517c6ff77c60c0ce0b6f))
- **other:** Remove memory and fix classification query ([`3d40377`](3d403774e79fbac78f055acf8c8fab95b040d2cb))
- **other:** Update project ([`1728c80`](1728c80d948d6cd8fd96042e0c97cb8365ca86f1))
- **other:** Update project ([`e57031d`](e57031da8b5c1212ed13529bfe510b03503a255b))
- **other:** Update evaluation ([`d534bb7`](d534bb780900a84b7801c225c533d5383ce94560))
- **other:** Update ([`32a1c7b`](32a1c7baa14b0a60fb5e151a4290570367e837d6))
- **other:** Update ([`84da9f7`](84da9f758cc2316ecd21d6a21c609dbe7b1b20eb))
- **other:** Add standard evaluation metrics ([`f4232ef`](f4232ef17da096f269150e3d89a454123cdedd01))
- **other:** Update eval ([`e7ac0b5`](e7ac0b59464a3f6ee49e94a76476e76b22294e71))
- **other:** Update eval ([`990d2ef`](990d2ef5b73aa37e9709c14f265dc30fda247d4b))
- **other:** Update eval ([`ef86847`](ef868477647ff0333cfbe4cdd3fc02c328ab0b26))
- **other:** Update eval ([`463648c`](463648c4d990502b0404b72da2b4b43e822af7da))
- **other:** Update agent eval ([`4a2b2aa`](4a2b2aa7b5b9b642cfa3afd2f49814cb51b53515))
- **other:** Remove docs ([`e19a879`](e19a879107166922e4939bbc01b4c56b9969aae9))
- **other:** Update evaluation ([`aabcc2b`](aabcc2b6172d61746a1f28b180117fe7a89e6688))
- **other:** Update eval ([`95b7e86`](95b7e8672800bb60dd09f88d1e3319da13276371))
- **other:** Update eval ([`74b4542`](74b4542ef10e398263f947b10c83115e95213253))
- **other:** Update evaluation ([`2b96c5e`](2b96c5e5fdedec4b2f57929023a4b9f2cf0ce79d))
- **other:** Update agent ([`25b3be1`](25b3be1b1d62a182e05251865a9e27a853be702d))
- **other:** Update evaluation ([`0190b37`](0190b373127f1f53b02485ae3b56dbafbd26cb60))
- **other:** Update eval ([`ba3d694`](ba3d6948da17dba5b27bbe14d2892d17bd377a4f))
- **other:** Update project ([`fc71c2f`](fc71c2fe10dc9a8af32ea9c51ebd8ef988d53eb1))
- **other:** Update readme ([`06f5c13`](06f5c133c69f1cec3befff92784c89628c7e7266))
- **other:** Add baseline ([`416f2b4`](416f2b4227b627ec03b439dc480eec10fb5a2c4a))
- **other:** Merge pull request #7 from MaiconKevyn/decomposition_query

update readme ([`2521c99`](2521c994e3de4cba15c372bb5ad45cecc6d88aca))
- **other:** Merge pull request #8 from MaiconKevyn/decomposition_query

update readme ([`ab5f109`](ab5f10987800a15da7a06b061774beffbd8537d2))
- **other:** Merge pull request #9 from MaiconKevyn/decomposition_query

delete old file ([`156c713`](156c713f93649beb3400e7fdaa8bc9a72b0a287d))
- **other:** Merge pull request #10 from MaiconKevyn/decomposition_query

Decomposition query ([`2f6ee88`](2f6ee88be8a88c8150a413ccbb42fe4d9c806a42))
- **other:** Merge pull request #11 from MaiconKevyn/decomposition_query

update database ([`759b39a`](759b39a679199b1f0ea707ad43b3f6bc8f99961d))
- **other:** Merge pull request #12 from MaiconKevyn/decomposition_query

Decomposition query ([`f2f917a`](f2f917a8c24cd6f4c8e14b4467c8fd470484c4ec))
- **other:** Merge pull request #13 from MaiconKevyn/database_migration

Database migration ([`ac60537`](ac60537e918d9132e2b30a7abb4119ff6bb7a2d4))
- **other:** Merge pull request #14 from MaiconKevyn/database_migration

Database migration ([`04f8218`](04f8218ce64b36d9951eb279899433ddb4b33090))
- **other:** Merge pull request #15 from MaiconKevyn/database_migration

update table selection node ([`0ce3da1`](0ce3da140aa706cd4d74e2d09c0fcd33660f0c79))
- **other:** Merge pull request #16 from MaiconKevyn/database_migration

update tools ([`9082da2`](9082da257733041d3851cb8e16ce853f515d6da6))
- **other:** Merge pull request #17 from MaiconKevyn/database_migration

add evaluation selected tables ([`221a212`](221a212631e45510b213448f2a1a370dc738f30e))
- **other:** Merge pull request #18 from MaiconKevyn/database_migration

add prompt template for all tables ([`e7c63e7`](e7c63e7b70fe65a99e520e81b65f52a62f77d09a))
- **other:** Merge pull request #19 from MaiconKevyn/database_migration

update project ([`222bc8f`](222bc8ffb983856c362977c47146a67be94e0844))
- **other:** Merge pull request #20 from MaiconKevyn/database_migration

update gitignore ([`3c33ef8`](3c33ef888c1f56c5adccbb24e6a4f34b0f19fd21))
- **other:** Merge pull request #21 from MaiconKevyn/database_migration

update project ([`b8071af`](b8071afa151afe418c4c7285ab1f5a86bc3bfafe))
- **other:** Merge pull request #22 from MaiconKevyn/database_migration

clean structure ([`7e0d40f`](7e0d40fad467a0d1cdbdd3cd44efcd369b32b973))
- **other:** Merge pull request #23 from MaiconKevyn/database_migration

update project structure ([`559e4d8`](559e4d82673bd429b164096c3635ea22c6e28c3b))
- **other:** Merge pull request #24 from MaiconKevyn/database_migration

Database migration ([`c62a9d4`](c62a9d4050372e61a9ff03730aa592063f4ca8bf))
- **other:** Merge pull request #25 from MaiconKevyn/database_migration

update project ([`57aab78`](57aab782a5bb622f71e5ecdce1130b9fbb0b6484))
- **other:** Merge pull request #26 from MaiconKevyn/database_migration

update requirements ([`deb4237`](deb42374dfd08e2b8b7c043043ce56ea0b91361e))
- **other:** Merge pull request #27 from MaiconKevyn/database_migration

Database migration ([`908ee39`](908ee39753d5a8dd1880f00613df2deb85e5110a))
- **other:** Merge pull request #28 from MaiconKevyn/database_migration

update project ([`1ad51f0`](1ad51f05fa6db01a7bafa00a971ca32391ba9e87))
- **other:** Merge pull request #29 from MaiconKevyn/database_migration

update readme ([`4ee46d8`](4ee46d8e49ee16019520823ac84dcaa000ecf5d5))
- **other:** Merge pull request #30 from MaiconKevyn/database_migration

update readme ([`e02ab43`](e02ab433906b883be3ae12ba8c77ceb570258228))
- **other:** Merge pull request #31 from MaiconKevyn/database_migration

update project ([`628cfc4`](628cfc430592b0b96e71805e55f93f51dfe15dda))
- **other:** Merge pull request #32 from MaiconKevyn/database_migration

remove env ([`f05a38c`](f05a38c9bd3db5077993ff8415ee1bae4f4e042a))
- **other:** Merge pull request #33 from MaiconKevyn/database_migration

Database migration ([`2626a8e`](2626a8e29112ce8e721c2323d7edd8eaada147f6))
- **other:** Merge pull request #34 from MaiconKevyn/database_migration

update project ([`9c64b7e`](9c64b7e4ec6a27fb82170c4266348ccdad1d7149))
- **other:** Merge pull request #35 from MaiconKevyn/database_migration

update README ([`297b061`](297b0613f06a0b21d1485c3a1e78635df65aa299))
- **other:** Merge pull request #36 from MaiconKevyn/database_migration

update project ([`36eaedb`](36eaedbc8bf7f90d878c944d5f424b540019f437))
- **other:** Merge pull request #37 from MaiconKevyn/database_migration

update readme ([`34dc0e5`](34dc0e52f889657dc9d429c3c1d9274a24ab64d8))
- **other:** Merge pull request #38 from MaiconKevyn/database_migration

update ([`5b57457`](5b574579a757794d72c05edceae0a2ea95805ab4))
- **other:** Merge pull request #39 from MaiconKevyn/memory_analysis_review

Memory analysis review ([`a0e29c3`](a0e29c3e44ed3946e22d421bec25d22ee2dd6a30))
- **other:** Merge pull request #40 from MaiconKevyn/evaluation_metrics

Evaluation metrics ([`2ef135f`](2ef135fb710009a2de6f20c57e26fafea50b24fd))
- **other:** Merge pull request #41 from MaiconKevyn/evaluation_metrics

Evaluation metrics ([`de92479`](de92479aa62d9cf9fbfaf7161f2ce35c7ece2dda))
- **other:** Merge pull request #42 from MaiconKevyn/evaluation_metrics

update ([`052612a`](052612a19ae30d72b7aa16832abb91c6ecd0113f))
- **other:** Merge pull request #43 from MaiconKevyn/evaluation_metrics

add standard evaluation metrics ([`11b5029`](11b50297b47213dbed7182b47232dd02ad654761))
- **other:** Merge pull request #44 from MaiconKevyn/evaluation_metrics

update eval ([`72b94a0`](72b94a050c514f524117b4097baa4914d51c7d68))
- **other:** Merge pull request #45 from MaiconKevyn/evaluation_metrics

update eval ([`f902ad1`](f902ad1bd16fc2b9f503281166e3a2e01e4434eb))
- **other:** Merge pull request #46 from MaiconKevyn/evaluation_metrics

update eval ([`b469d0a`](b469d0ae3b5867af766578217a77878432c24c4b))
- **other:** Merge pull request #47 from MaiconKevyn/evaluation_metrics

update eval ([`c84716b`](c84716b6789849a7a62e8eee64f21c28fba828e5))
- **other:** Merge pull request #48 from MaiconKevyn/evaluation_metrics

update agent eval ([`fa09a78`](fa09a7889611328153969f94112476d7e2a09619))
- **other:** Merge pull request #49 from MaiconKevyn/evaluation_metrics

remove docs ([`bc6afe1`](bc6afe19cea5f822abe11ceb3f96299c70ce8881))
- **other:** Merge pull request #50 from MaiconKevyn/evaluation_metrics

update evaluation ([`82574a9`](82574a914065d8f2398968734d00e2255450b119))
- **other:** Merge pull request #51 from MaiconKevyn/evaluation_metrics

update eval ([`888e265`](888e265c83e7ec2b741ad37acadb4e8ad73f9cff))
- **other:** Merge pull request #52 from MaiconKevyn/evaluation_metrics

Evaluation metrics ([`a2fad1a`](a2fad1a183a4b62278d9ef15eb287e0b4bad3770))
- **other:** Merge pull request #53 from MaiconKevyn/evaluation_metrics

update agent ([`c9dd1ea`](c9dd1ea571dfd3c6ea6299d22614395f3efd06e7))
- **other:** Merge pull request #54 from MaiconKevyn/multi_agent_arch

update evaluation ([`358a58f`](358a58fa6974ca03a6c76307f5dd9cfb4ecd9985))
- **other:** Merge pull request #55 from MaiconKevyn/multi_agent_arch

update eval ([`9ea9add`](9ea9add77053056963172033b7c8730cd129d192))
- **other:** Merge pull request #56 from MaiconKevyn/multi_agent_arch

update project ([`cc35b70`](cc35b70bd4ae775b6d22c462fd162e73032b4a95))
- **other:** Add rag ([`b826959`](b826959e59033326f5d0b032ea28e0486c34d6dc))
- **other:** Merge pull request #57 from MaiconKevyn/generalize_models

add rag ([`18f6695`](18f66959e16fbfe7aae1ff87c26fb1cfb6761499))
- **other:** Update agent ([`d97cebd`](d97cebdedf3e5e77e4f3aa734b161ac3a7beff0f))
- **other:** Update agent ([`8002862`](80028629ccadea98d0658ff8703abbcd9a8106b5))
- **other:** Update agent ([`a11d011`](a11d01151a53a1ad0f47adc8061d6b23d316c2ea))
- **other:** Merge pull request #58 from MaiconKevyn/generalize_models

Generalize models ([`959606d`](959606dd1aae2ea176587685676797444dc1ebb8))
- **other:** Merge pull request #59 from MaiconKevyn/refactored_agent

Refactored agent ([`e8cf39c`](e8cf39caaa9a188a142f65704991c2574cf130aa))
- **other:** Merge branch 'main' into refactored_agent ([`c8fcf6e`](c8fcf6ef3545509e21639867233032a2e46de616))
- **other:** Update agente to use openai models ([`8948aef`](8948aef2437a7f02590e477aa1bad2f62aab097c))
- **other:** Update agent ([`4187fb7`](4187fb732f496d8536e42d3aa0a2eec8f588204b))
- **other:** Update agent ([`c1d11c6`](c1d11c6ae56c8ffb520a96a3710d0cbfe0cc026a))
- **other:** Separe node.py in files ([`bab1c02`](bab1c021f810544d3e63b33c4eddc3a2d57152d6))
- **other:** Update agent ([`4db15ca`](4db15ca1fac06d477cc88e4a8e68af0fa7c6967a))
- **other:** Update agent ([`e80f2eb`](e80f2eba160d5cf21b4fd79124db8250794dee0e))
- **other:** Add multi-query decomposition system (plan-and-execute)

The LLM can now decide to split a question into N SQL sub-queries,
execute them (with sequential dependency support), and synthesize
a single natural language response.

Changes:
- state.py: Add SubQuery, QueryPlan dataclasses + query_plan,
  sub_query_results, is_multi_query fields to MessagesStateTXT2SQL
- query_planner.py: New node that decides single vs multi strategy
  using structured JSON output; graceful fallback to single on error
- multi_executor.py: New node that topologically sorts sub-queries
  by dependency, generates SQL using full RULES A-O prompt
  (build_sql_generation_messages), and executes each via sql_db_query
- result_synthesizer.py: New node that synthesizes N result sets into
  a single Portuguese natural language response
- sql_generation.py: Extract build_sql_generation_messages() helper
  (RULES A-O + table templates + hints) so multi_executor reuses
  identical prompt logic; generate_sql_node now calls this helper
- workflow.py: Wire new nodes; get_schema -> query_planner ->
  {generate_sql (single) | multi_sql_executor -> result_synthesizer}
- nodes.py: Re-export new nodes

Tested:
- 2-state query: RS + MA deaths in 2019 → 2/2 sub-queries succeed
- 3-state query: SP + RJ + MG births in 2020 → 3/3 sub-queries succeed
- Single-query path unchanged: 25/25 existing tests pass

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com> ([`377e33f`](377e33fb33abbda20fe2b15cb9e20cbdb704bc62))
- **other:** Add force_single_query flag for evaluation mode

The multi-query planner runs in production but evaluation must compare
predicted_sql against a single GT SQL. force_single_query=True bypasses
the multi-query path so evaluation stays comparable with prior runs.

- state.py: Add force_single_query field (default False)
- workflow.py: route_after_query_planner respects force_single_query;
  execute_sql_workflow passes it to create_initial_messages_state
- orchestrator.py: process_query exposes force_single_query param
- evaluation/dag/tasks.py: pass force_single_query=True in eval calls

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com> ([`0550bf8`](0550bf831e5f5b9e0ad9164d399ea8247e78fe0a))
- **other:** Update agent ([`1625b96`](1625b9621323c3b76b3d303aa674eb2dd352c58b))
- **other:** Stop tracking CLAUDE.md ([`00e93a9`](00e93a9974fac9fb67ef9eee030cf4eec1f5f985))
- **other:** Update readme ([`775da41`](775da41079c0abacbb9c943fab1b297696e92721))
- **other:** Update log rotate script ([`44584a4`](44584a4aed36cd213c0ff632045a6e6e7eab268e))
- **other:** Update gitignore ([`5541e60`](5541e60b7b4146d5cee5fece05481568d1d4926c))


