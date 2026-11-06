import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'services/api_service.dart';

void main() => runApp(const AITradeApp());

const cyan = Color(0xFF00E5C3);
const blue = Color(0xFF39A8FF);
const violet = Color(0xFF9B72FF);
const green = Color(0xFF21D6A1);
const red = Color(0xFFFF647C);

class AITradeApp extends StatefulWidget {
  const AITradeApp({super.key});
  @override
  State<AITradeApp> createState() => _AITradeAppState();
}

class _AITradeAppState extends State<AITradeApp> {
  bool dark = true;
  bool english = false;
  String mode = 'PAPER';

  @override
  Widget build(BuildContext context) {
    final bg = dark ? const Color(0xFF070B16) : const Color(0xFFF1F5FA);
    final panel = dark ? const Color(0xFF101A2B) : Colors.white;
    final text = dark ? Colors.white : const Color(0xFF152238);
    final muted = dark ? const Color(0xFF8997B0) : const Color(0xFF718096);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: dark ? Brightness.dark : Brightness.light,
        scaffoldBackgroundColor: bg,
        colorScheme: ColorScheme.fromSeed(
          seedColor: cyan,
          brightness: dark ? Brightness.dark : Brightness.light,
          surface: panel,
        ),
        useMaterial3: true,
      ),
      home: Directionality(
        textDirection: english ? TextDirection.ltr : TextDirection.rtl,
        child: TradeShell(
          dark: dark,
          english: english,
          mode: mode,
          bg: bg,
          panel: panel,
          text: text,
          muted: muted,
          onTheme: () => setState(() => dark = !dark),
          onLanguage: () => setState(() => english = !english),
          onMode: (v) => setState(() => mode = v),
        ),
      ),
    );
  }
}

class TradeShell extends StatefulWidget {
  final bool dark, english;
  final String mode;
  final Color bg, panel, text, muted;
  final VoidCallback onTheme, onLanguage;
  final ValueChanged<String> onMode;

  const TradeShell({
    super.key,
    required this.dark,
    required this.english,
    required this.mode,
    required this.bg,
    required this.panel,
    required this.text,
    required this.muted,
    required this.onTheme,
    required this.onLanguage,
    required this.onMode,
  });

  @override
  State<TradeShell> createState() => _TradeShellState();
}

class _TradeShellState extends State<TradeShell>
    with TickerProviderStateMixin {
  int page = 0;
  bool running = true;
  bool apiOnline = false;
  bool apiBusy = false;
  Map<String, dynamic> paperData = {};
  Map<String, dynamic> agentControls = {};
  final Set<String> closingPositionIds = {};
  late final AnimationController pulse = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 9),
  )..repeat();

  bool get en => widget.english;
  String tr(String ar, String eng) => en ? eng : ar;

  @override
  void initState() {
    super.initState();
    _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    if (apiBusy) return;
    setState(() => apiBusy = true);

    try {
      final data = await ApiService.status();
      if (!mounted) return;

      final paper = data['paper'];
      final controls = data['controls'];
      final mergedPaper = paper is Map
          ? Map<String, dynamic>.from(paper)
          : <String, dynamic>{};

      if (widget.mode.toUpperCase() == 'DEMO') {
        final demo = await ApiService.demoPositions();
        final source = demo['positions'] ??
            demo['open_positions'] ??
            demo['items'] ??
            (demo['data'] is Map
                ? (demo['data']['positions'] ??
                    demo['data']['open_positions'])
                : null);

        final positions = source is List
            ? source.whereType<Map>().map((item) {
                final position = Map<String, dynamic>.from(item);
                position['id'] = position['id'] ??
                    position['position_id'] ??
                    position['trade_id'] ??
                    '';
                return position;
              }).where((item) => item['id'].toString().isNotEmpty).toList()
            : <Map<String, dynamic>>[];

        mergedPaper['open_positions'] = positions;
        mergedPaper['open_count'] = positions.length;
      }

      setState(() {
        apiOnline = true;
        paperData = mergedPaper;
        agentControls = controls is Map
            ? Map<String, dynamic>.from(controls)
            : {};
      });
    } catch (e) {
      if (mounted) {
        setState(() => apiOnline = false);
      }
    } finally {
      if (mounted) {
        setState(() => apiBusy = false);
      }
    }
  }
  Future<void> _closePaperPosition(Map<String, dynamic> position) async {
    final id = '${position['id'] ?? position['position_id'] ?? position['trade_id'] ?? ''}';
    if (id.isEmpty || closingPositionIds.contains(id)) return;

    final isDemo = widget.mode.toUpperCase() == 'DEMO';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: widget.panel,
        title: Text(tr('تأكيد إغلاق الصفقة', 'Confirm position close')),
        content: Text(
          tr(
            'سيتم إغلاق ${position['symbol'] ?? ''} في وضع ${isDemo ? 'DEMO' : 'PAPER'}. هذا الإجراء خاص بهذا المركز فقط.',
            'This will close ${position['symbol'] ?? ''} in ${isDemo ? 'DEMO' : 'PAPER'} mode. Only this position will be affected.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(tr('إلغاء', 'Cancel')),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: red),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(tr('إغلاق الصفقة', 'Close position')),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    setState(() => closingPositionIds.add(id));
    try {
      final result = isDemo
          ? await ApiService.closeDemoTrade(positionId: id)
          : await ApiService.closePaperTrade(positionId: id);

      if (!mounted) return;

      final success =
          result['success'] == true || result['ok'] == true;

      if (success) {
        notify(tr(
          'تم إرسال طلب إغلاق المركز.',
          'Position close request submitted.',
        ));
        await _refreshStatus();
      } else {
        notify(
          '${tr('تعذر إغلاق المركز: ', 'Could not close position: ')}'
          '${result['reason'] ?? result['error'] ?? 'Unknown error'}',
        );
      }
    } catch (error) {
      if (mounted) {
        notify('${tr('خطأ أثناء الإغلاق: ', 'Close error: ')}$error');
      }
    } finally {
      if (mounted) {
        setState(() => closingPositionIds.remove(id));
      }
    }
  }
  void _applyStatus(Map<String, dynamic> data) {
    final paper = data['paper'];
    final controls = data['controls'];
    apiOnline = true;
    paperData = paper is Map
        ? Map<String, dynamic>.from(paper)
        : {};
    agentControls = controls is Map
        ? Map<String, dynamic>.from(controls)
        : {};
  }

  bool get allAgentsEnabled {
    const domains = ['futures', 'spot', 'alpha'];
    return domains.every((d) =>
        agentControls[d] is Map &&
        (agentControls[d]['enabled'] == true));
  }

  Future<void> _changeMode(String value) async {
    if (!apiOnline || apiBusy) return;

    setState(() => apiBusy = true);
    try {
      final result = await ApiService.setMode(value);
      if (!mounted) return;

      if (result['success'] == true && result['mode'] == value) {
        widget.onMode(value);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(
            tr('تم تغيير الوضع إلى $value', 'Mode changed to $value'),
          )),
        );
      } else {
        throw Exception(result['reason'] ?? 'Mode change rejected');
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(
            '${tr('تعذر تغيير الوضع: ', 'Mode change failed: ')}$error',
          )),
        );
      }
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
  }

  Future<void> _setAgent(String domain, bool enabled) async {
    if (!apiOnline || apiBusy) return;
    setState(() => apiBusy = true);

    try {
      if (enabled) {
        await ApiService.resumeAgent(domain);
      } else {
        await ApiService.stopAgent(domain);
      }

      final data = await ApiService.status();
      if (!mounted) return;
      setState(() => _applyStatus(data));

      notify(enabled
          ? tr('تم إرسال طلب استئناف الوكيل', 'Agent resume request sent')
          : tr('تم إرسال طلب إيقاف الوكيل', 'Agent stop request sent'));
    } catch (e) {
      if (mounted) {
        notify(tr('تعذّر تنفيذ الأمر: $e', 'Action failed: $e'));
      }
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
  }

  Future<void> _setAllAgents(bool enabled) async {
    if (!apiOnline || apiBusy) return;
    setState(() => apiBusy = true);

    try {
      if (enabled) {
        await ApiService.resumeAll();
      } else {
        await ApiService.emergencyStop();
      }

      final data = await ApiService.status();
      if (!mounted) return;
      setState(() => _applyStatus(data));

      notify(enabled
          ? tr('تم إرسال طلب استئناف جميع الوكلاء',
              'Resume-all request sent')
          : tr('تم إرسال طلب الإيقاف الشامل',
              'Emergency-stop request sent'));
    } catch (e) {
      if (mounted) {
        notify(tr('تعذّر تنفيذ الأمر: $e', 'Action failed: $e'));
      }
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
  }

  @override
  void dispose() {
    pulse.dispose();
    super.dispose();
  }

  void notify(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: widget.panel,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final titles = en
        ? ['Dashboard', 'Agents', 'Markets', 'Portfolio', 'Settings']
        : ['الرئيسية', 'الوكلاء', 'الأسواق', 'المحفظة', 'الإعدادات'];

    final pages = [
      _home(),
      _agents(),
      _markets(),
      _portfolio(),
      _settings(),
    ];

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _topBar(),
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: KeyedSubtree(
                  key: ValueKey(page),
                  child: pages[page],
                ),
              ),
            ),
            _bottomBar(titles),
          ],
        ),
      ),
    );
  }

  Widget _topBar() => Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
        child: Row(
          children: [
            Container(
              width: 43,
              height: 43,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(15),
                gradient: const LinearGradient(
                  colors: [cyan, blue, violet],
                ),
                boxShadow: [
                  BoxShadow(
                    color: cyan.withOpacity(.25),
                    blurRadius: 20,
                  )
                ],
              ),
              child: const Icon(Icons.auto_awesome, color: Color(0xFF07111D)),
            ),
            const SizedBox(width: 9),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'AI TRADE',
                  style: TextStyle(
                    color: widget.text,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 1.5,
                  ),
                ),
                Text(
                  tr('مركز القيادة الذكي', 'INTELLIGENT COMMAND'),
                  style: TextStyle(color: widget.muted, fontSize: 9),
                ),
              ],
            ),
            const Spacer(),
            _topButton(
              en ? 'AR' : 'EN',
              Icons.language,
              widget.onLanguage,
            ),
            const SizedBox(width: 5),
            _topButton(
              '',
              widget.dark ? Icons.light_mode : Icons.dark_mode,
              widget.onTheme,
            ),
            const SizedBox(width: 5),
            _topButton(
              '',
              Icons.notifications_none_rounded,
              () => notify(tr('لا توجد تنبيهات جديدة', 'No new alerts')),
            ),
          ],
        ),
      );

  Widget _topButton(String label, IconData icon, VoidCallback action) =>
      InkWell(
        onTap: action,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          height: 38,
          padding: const EdgeInsets.symmetric(horizontal: 9),
          decoration: BoxDecoration(
            color: widget.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: cyan.withOpacity(.18)),
          ),
          child: Row(
            children: [
              Icon(icon, color: cyan, size: 17),
              if (label.isNotEmpty) ...[
                const SizedBox(width: 4),
                Text(
                  label,
                  style: TextStyle(
                    color: widget.text,
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ]
            ],
          ),
        ),
      );

  Widget _modeSelector() => Container(
        padding: const EdgeInsets.all(5),
        decoration: BoxDecoration(
          color: widget.panel,
          borderRadius: BorderRadius.circular(15),
          border: Border.all(color: cyan.withOpacity(.18)),
        ),
        child: Row(
          children: [
            _modeButton('PAPER', tr('ورقي', 'Paper'), cyan),
            _modeButton('DEMO', tr('تجريبي', 'Demo'), blue),
            _modeButton('LIVE', tr('حقيقي', 'Live'), red),
          ],
        ),
      );

  Widget _modeButton(String value, String label, Color color) {
    final selected = widget.mode == value;
    return Expanded(
      child: InkWell(
        onTap: () async {
          if (value == 'LIVE') {
            showDialog(
              context: context,
              builder: (ctx) => AlertDialog(
                backgroundColor: widget.panel,
                title: Text(tr('التداول الحقيقي مقفل', 'Live trading locked')),
                content: Text(
                  tr(
                    'لن يتم تفعيل التداول الحقيقي قبل ربط API آمن واختبار محرك التنفيذ وإدارة المخاطر.',
                    'Live trading requires secure API integration, execution testing and risk controls.',
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('OK'),
                  )
                ],
              ),
            );
            return;
          }
          await _changeMode(value);
        },
        borderRadius: BorderRadius.circular(11),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 3),
          decoration: BoxDecoration(
            color: selected ? color.withOpacity(.16) : Colors.transparent,
            borderRadius: BorderRadius.circular(11),
            border: Border.all(
              color: selected ? color.withOpacity(.6) : Colors.transparent,
            ),
          ),
          child: Column(
            children: [
              Text(
                value,
                style: TextStyle(
                  color: selected ? color : widget.muted,
                  fontWeight: FontWeight.w900,
                  fontSize: 10,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                label,
                style: TextStyle(
                  color: selected ? widget.text : widget.muted,
                  fontSize: 9,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _home() => ListView(
        key: const PageStorageKey('home'),
        padding: const EdgeInsets.fromLTRB(15, 0, 15, 22),
        children: [
          _modeSelector(),
          const SizedBox(height: 13),
          _hero(),
          const SizedBox(height: 15),
          _portfolioCard(),
          const SizedBox(height: 20),
          _heading(
            tr('نبض السوق', 'MARKET PULSE'),
            tr('بيانات توضيحية حالياً', 'PREVIEW DATA'),
            Icons.candlestick_chart,
          ),
          const SizedBox(height: 10),
          _chart(true),
          const SizedBox(height: 18),
          _heading(
            tr('مركز التنفيذ', 'EXECUTION CENTER'),
            widget.mode,
            Icons.bolt,
          ),
          const SizedBox(height: 9),
          _quickTrade(),
          const SizedBox(height: 18),
          _heading(
            tr('فريق الوكلاء', 'AGENT NETWORK'),
            '3 AGENTS',
            Icons.hub,
          ),
          const SizedBox(height: 10),
          _agentRow('futures', 'FUTURES AGENT', tr('العقود الآجلة', 'Futures'), cyan),
          _agentRow('spot', 'SPOT AGENT', tr('السوق الفوري', 'Spot'), blue),
          _agentRow('alpha', 'ALPHA AGENT', tr('اكتشاف الأصول', 'Asset discovery'), violet),
          const SizedBox(height: 12),
          _activityCard(),
        ],
      );

  Widget _hero() => Container(
        height: 245,
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(25),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF102E40),
              Color(0xFF171832),
              Color(0xFF0B1223),
            ],
          ),
          border: Border.all(color: cyan.withOpacity(.35)),
          boxShadow: [
            BoxShadow(color: cyan.withOpacity(.08), blurRadius: 28)
          ],
        ),
        child: Stack(
          children: [
            Positioned.fill(child: CustomPaint(painter: GridPainter())),
            Positioned(
              left: -30,
              top: 5,
              child: AnimatedBuilder(
                animation: pulse,
                builder: (_, __) => SizedBox(
                  width: 230,
                  height: 230,
                  child: CustomPaint(painter: OrbPainter(pulse.value)),
                ),
              ),
            ),
            Positioned(
              right: 17,
              top: 23,
              child: SizedBox(
                width: 205,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.bolt, color: cyan, size: 17),
                        SizedBox(width: 5),
                        Text(
                          'MULTI AGENT AI',
                          style: TextStyle(
                            color: cyan,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 19),
                    Text(
                      tr('ثلاثة وكلاء.', 'Three Agents.'),
                      style: TextStyle(
                        color: widget.text,
                        fontSize: 25,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    Text(
                      tr('عقل تداول واحد', 'One Trading Brain'),
                      style: const TextStyle(
                        color: cyan,
                        fontSize: 23,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 9),
                    Text(
                      tr(
                        'تحليل مستقل، إدارة مخاطر مشتركة، وقرارات منسقة.',
                        'Independent analysis, shared risk management and coordinated decisions.',
                      ),
                      textAlign: TextAlign.right,
                      style: const TextStyle(
                        color: Color(0xFFB5C8D8),
                        fontSize: 11,
                        height: 1.5,
                      ),
                    ),
                    const SizedBox(height: 14),
                    _pill(
                      tr('النظام في وضع الاستعداد', 'SYSTEM STANDBY'),
                      cyan,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      );

  Widget _portfolioCard() {
    final balance = double.tryParse('${paperData['balance'] ?? ''}');
    final openCount = paperData['open_count'] ?? 0;
    final totalTrades = paperData['total_trades'] ?? 0;
    final balanceText =
        balance == null ? '—' : '\$${balance.toStringAsFixed(2)}';

    return _panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                tr('رصيد محاكاة PAPER', 'PAPER SIMULATION BALANCE'),
                style: TextStyle(color: widget.muted, fontSize: 11),
              ),
              const Spacer(),
              _pill(apiOnline ? 'PAPER' : tr('غير متصل', 'OFFLINE'),
                  apiOnline ? cyan : red),
              IconButton(
                tooltip: tr('تحديث البيانات', 'Refresh data'),
                onPressed: apiBusy ? null : _refreshStatus,
                icon: Icon(Icons.refresh, color: widget.muted, size: 19),
              ),
            ],
          ),
          const SizedBox(height: 9),
          Text(
            apiOnline ? balanceText : '—',
            style: TextStyle(
              color: widget.text,
              fontSize: 34,
              fontWeight: FontWeight.w900,
            ),
          ),
          Text(
            apiOnline
                ? tr('بيانات فعلية من محرك PAPER المحلي',
                    'Live data from the local PAPER engine')
                : tr('شغّل خادم Termux لعرض بيانات المحاكاة',
                    'Start the Termux server to load simulation data'),
            style: TextStyle(color: widget.muted, fontSize: 10),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              _metric(tr('الربح', 'PROFIT'), '—', widget.muted),
              _metric(tr('المراكز المفتوحة', 'OPEN POSITIONS'),
                  apiOnline ? '$openCount' : '—', widget.text),
              _metric(tr('إجمالي الصفقات', 'TOTAL TRADES'),
                  apiOnline ? '$totalTrades' : '—', widget.text),
            ],
          ),
        ],
      ),
    );
  }

  Widget _quickTrade() => _panel(
        border: violet.withOpacity(.35),
        child: Column(
          children: [
            Row(
              children: [
                const Icon(Icons.bolt, color: violet),
                const SizedBox(width: 7),
                Text(
                  tr('محاكاة صفقة سريعة', 'QUICK TRADE SIMULATION'),
                  style: TextStyle(
                    color: widget.text,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 13),
            Row(
              children: [
                Expanded(
                  child: _tradeButton(
                    tr('شراء / LONG', 'BUY / LONG'),
                    green,
                    () => _confirmTrade('LONG'),
                  ),
                ),
                const SizedBox(width: 9),
                Expanded(
                  child: _tradeButton(
                    tr('بيع / SHORT', 'SELL / SHORT'),
                    red,
                    () => _confirmTrade('SHORT'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              tr(
                'محاكاة فقط — لا يتم إرسال أوامر حقيقية.',
                'Simulation only — no real orders are sent.',
              ),
              style: TextStyle(color: widget.muted, fontSize: 9),
            ),
          ],
        ),
      );

  void _confirmTrade(String side) {
    final isDemo = widget.mode.toUpperCase() == 'DEMO';

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: widget.panel,
        title: Text(
          tr(
            isDemo ? 'تأكيد صفقة Futures DEMO' : 'تأكيد المحاكاة',
            isDemo ? 'Confirm DEMO Futures Trade' : 'Confirm simulation',
          ),
        ),
        content: Text(
          isDemo
              ? tr(
                  'سيتم إرسال أمر $side على BTCUSDT إلى Binance Futures Testnet، مع إعداد مخاطرة 0.5% ورافعة 1x. لن يتم استخدام أموال حقيقية.',
                  'A $side BTCUSDT order will be sent to Binance Futures Testnet with 0.5% risk and 1x leverage. No real funds will be used.',
                )
              : tr(
                  'أنت في وضع PAPER. لن يتم إرسال أي أمر إلى Binance.',
                  'You are in PAPER mode. No Binance order will be sent.',
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(tr('إلغاء', 'Cancel')),
          ),
          FilledButton(
            onPressed: apiBusy
                ? null
                : () async {
                    Navigator.pop(ctx);

                    if (!isDemo) {
                      notify(tr(
                        'وضع PAPER لا يرسل أوامر إلى Binance.',
                        'PAPER mode does not send Binance orders.',
                      ));
                      return;
                    }

                    if (!apiOnline) {
                      notify(tr(
                        'خادم التداول غير متصل.',
                        'Trading server is offline.',
                      ));
                      return;
                    }

                    setState(() => apiBusy = true);
                    try {
                      final result = await ApiService.openDemoTrade(
                        symbol: 'BTCUSDT',
                        direction: side,
                        riskPct: 0.5,
                        leverage: 1,
                      );

                      if (!mounted) return;

                      final success = result['success'] == true ||
                          result['ok'] == true;

                      notify(
                        success
                            ? tr(
                                'تم إرسال طلب Futures DEMO.',
                                'Futures DEMO order submitted.',
                              )
                            : '${result['reason'] ?? result['error'] ?? 'Order rejected'}',
                      );

                      if (success) {
                        await _refreshStatus();
                      }
                    } catch (e) {
                      if (mounted) {
                        notify('${tr('فشل تنفيذ الصفقة', 'Trade failed')}: $e');
                      }
                    } finally {
                      if (mounted) {
                        setState(() => apiBusy = false);
                      }
                    }
                  },
            child: Text(tr('تأكيد', 'Confirm')),
          ),
        ],
      ),
    );
  }

  Widget _agents() => ListView(
        padding: const EdgeInsets.all(15),
        children: [
          _pageHeading(
            tr('شبكة الوكلاء العصبية', 'NEURAL AGENT NETWORK'),
            'LIVE TOPOLOGY PREVIEW',
          ),
          const SizedBox(height: 12),
          Container(
            height: 285,
            decoration: BoxDecoration(
              color: widget.panel,
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: cyan.withOpacity(.25)),
            ),
            child: AnimatedBuilder(
              animation: pulse,
              builder: (_, __) => CustomPaint(
                painter: NetworkPainter(pulse.value),
                child: const SizedBox.expand(),
              ),
            ),
          ),
          const SizedBox(height: 15),
          _agentRow('futures', 'FUTURES AGENT',
              tr('العقود الآجلة', 'Futures'), cyan),
          _agentRow('spot', 'SPOT AGENT',
              tr('السوق الفوري', 'Spot'), blue),
          _agentRow('alpha', 'ALPHA AGENT',
              tr('اكتشاف الأصول', 'Asset discovery'), violet),
          const SizedBox(height: 12),
          _panel(
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        tr('حالة الوكلاء', 'AGENT STATUS'),
                        style: TextStyle(
                          color: widget.text,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    Text(
                      !apiOnline
                          ? tr('غير متصل', 'OFFLINE')
                          : allAgentsEnabled
                              ? tr('جميع الوكلاء يعملون', 'ALL ACTIVE')
                              : tr('بعض الوكلاء متوقفون', 'PARTIALLY STOPPED'),
                      style: TextStyle(
                        color: !apiOnline
                            ? red
                            : allAgentsEnabled
                                ? green
                                : widget.muted,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: !apiOnline || apiBusy
                        ? null
                        : () => _setAllAgents(!allAgentsEnabled),
                    icon: Icon(allAgentsEnabled
                        ? Icons.pause_circle
                        : Icons.play_arrow),
                    label: Text(allAgentsEnabled
                        ? tr('إيقاف شامل للطوارئ', 'EMERGENCY STOP ALL')
                        : tr('استئناف جميع الوكلاء', 'RESUME ALL AGENTS')),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  tr(
                    'الإيقاف يمنع فتح صفقات جديدة فقط، ولا يغلق المراكز المفتوحة.',
                    'Stopping prevents new trades only; open positions remain open.',
                  ),
                  textAlign: TextAlign.center,
                  style: TextStyle(color: widget.muted, fontSize: 10),
                ),
                if (!apiOnline)
                  Text(
                    tr('شغّل خادم Termux أولاً',
                        'Start the Termux server first'),
                    style: TextStyle(color: red, fontSize: 10),
                  ),
              ],
            ),
          ),
        ],
      );

  Widget _markets() => ListView(
        padding: const EdgeInsets.all(15),
        children: [
          _pageHeading(tr('مركز الأسواق', 'MARKET INTELLIGENCE'), 'MARKET DATA'),
          const SizedBox(height: 12),
          _chart(false),
          const SizedBox(height: 15),
          _heading(tr('قائمة المراقبة', 'WATCHLIST'), 'PREVIEW', Icons.star),
          const SizedBox(height: 10),
          _coin('₿', 'BTC / USDT', 'Bitcoin', '\$67,420', '+2.41%', cyan),
          _coin('Ξ', 'ETH / USDT', 'Ethereum', '\$3,520', '+1.28%', blue),
          _coin('◎', 'SOL / USDT', 'Solana', '\$184.32', '-0.74%', violet),
          const SizedBox(height: 8),
          Text(
            tr(
              'الأسعار المعروضة توضيحية وليست أسعار Binance الحية.',
              'Illustrative prices — not live Binance prices.',
            ),
            textAlign: TextAlign.center,
            style: TextStyle(color: widget.muted, fontSize: 10),
          ),
        ],
      );

  Widget _openPositionsSection() {
    final raw = paperData['open_positions'];
    final positions = raw is List
        ? raw
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList()
        : <Map<String, dynamic>>[];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _heading(
          tr('المراكز المفتوحة', 'OPEN POSITIONS'),
          '${positions.length} OPEN',
          Icons.swap_horiz,
        ),
        const SizedBox(height: 10),
        if (positions.isEmpty)
          _panel(
            child: Center(
              child: Text(
                tr('لا توجد مراكز مفتوحة حالياً', 'No open positions'),
                style: TextStyle(color: widget.muted),
              ),
            ),
          )
        else
          ...positions.map((position) {
            final id = '${position['id'] ?? position['position_id'] ?? position['trade_id'] ?? ''}';
            final symbol = '${position['symbol'] ?? '—'}';
            final direction = '${position['direction'] ?? '—'}'.toUpperCase();
            final domain = '${position['domain'] ?? '—'}'.toUpperCase();
            final entry = '${position['entry_price'] ?? '—'}';
            final quantity = '${position['remaining_quantity'] ?? position['quantity'] ?? '—'}';
            final stop = position['stop_loss']?.toString() ?? '—';
            final target = position['take_profit']?.toString() ?? '—';
            final isClosing = closingPositionIds.contains(id);
            final isShort = direction == 'SHORT';

            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _panel(
                border: (isShort ? red : cyan).withOpacity(.28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            symbol,
                            style: TextStyle(
                              color: widget.text,
                              fontWeight: FontWeight.w900,
                              fontSize: 16,
                            ),
                          ),
                        ),
                        _pill(direction, isShort ? red : green),
                        const SizedBox(width: 6),
                        _pill(domain, blue),
                      ],
                    ),
                    const SizedBox(height: 13),
                    Row(
                      children: [
                        Expanded(child: _metric(tr('سعر الدخول', 'ENTRY'), entry, widget.text)),
                        Expanded(child: _metric(tr('الكمية المتبقية', 'REMAINING QTY'), quantity, widget.text)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(child: _metric('STOP LOSS', stop, red)),
                        Expanded(child: _metric('TAKE PROFIT', target, green)),
                      ],
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: red.withOpacity(.16),
                          foregroundColor: red,
                        ),
                        onPressed: !apiOnline || isClosing
                            ? null
                            : () => _closePaperPosition(position),
                        icon: isClosing
                            ? const SizedBox(
                                width: 17,
                                height: 17,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.close_rounded),
                        label: Text(
                          isClosing
                              ? tr('جارٍ الإغلاق...', 'Closing...')
                              : tr('إغلاق هذا المركز', 'Close this position'),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
      ],
    );
  }

  Widget _portfolio() => ListView(
        padding: const EdgeInsets.all(15),
        children: [
          _pageHeading(tr('المحفظة والتحليلات', 'PORTFOLIO ANALYTICS'), 'ACCOUNT'),
          const SizedBox(height: 14),
          _portfolioCard(),
          const SizedBox(height: 16),
          _openPositionsSection(),
          const SizedBox(height: 16),
          _heading(tr('توزيع رأس المال', 'CAPITAL ALLOCATION'), 'DEMO', Icons.pie_chart),
          const SizedBox(height: 10),
          _panel(
            child: Row(
              children: [
                SizedBox(
                  width: 115,
                  height: 115,
                  child: CustomPaint(painter: DonutPainter()),
                ),
                const SizedBox(width: 17),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _legend(cyan, tr('متاح 100%', 'Available 100%')),
                      const SizedBox(height: 13),
                      _legend(blue, 'Spot 0%'),
                      const SizedBox(height: 13),
                      _legend(violet, 'Futures 0%'),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 17),
          _heading(tr('سجل الصفقات', 'TRADE HISTORY'), 'ACTIVITY', Icons.receipt_long),
          const SizedBox(height: 10),
          _panel(
            child: Center(
              child: Column(
                children: [
                  Icon(Icons.receipt_long, color: widget.muted, size: 35),
                  const SizedBox(height: 9),
                  Text(
                    tr('لا توجد صفقات مسجلة', 'No trades recorded'),
                    style: TextStyle(color: widget.muted),
                  ),
                ],
              ),
            ),
          ),
        ],
      );

  Widget _settings() => ListView(
        padding: const EdgeInsets.all(15),
        children: [
          _pageHeading(tr('الإعدادات والتحكم', 'SYSTEM CONFIGURATION'), 'PREFERENCES'),
          const SizedBox(height: 14),
          _panel(
            child: Column(
              children: [
                _setting(
                  Icons.language,
                  tr('لغة التطبيق', 'App language'),
                  en ? 'English' : 'العربية',
                  TextButton(
                    onPressed: widget.onLanguage,
                    child: Text(en ? 'العربية' : 'English'),
                  ),
                ),
                _setting(
                  Icons.palette_outlined,
                  tr('المظهر', 'Appearance'),
                  widget.dark ? tr('داكن', 'Dark') : tr('فاتح', 'Light'),
                  Switch(
                    value: widget.dark,
                    onChanged: (_) => widget.onTheme(),
                    activeColor: cyan,
                  ),
                ),
                _setting(
                  Icons.science_outlined,
                  tr('وضع التداول', 'Trading mode'),
                  widget.mode,
                  const Icon(Icons.tune, color: cyan),
                ),
                _setting(
                  Icons.shield_outlined,
                  tr('محرك إدارة المخاطر', 'Risk management'),
                  tr('حماية رأس المال', 'Capital protection'),
                  const Icon(Icons.verified_user, color: green),
                ),
                _setting(
                  Icons.key_rounded,
                  'Binance API',
                  tr('غير متصل بالتطبيق', 'Not connected to app'),
                  const Icon(Icons.lock_outline, color: widgetMuted),
                ),
              ],
            ),
          ),
          const SizedBox(height: 15),
          _panel(
            border: red.withOpacity(.3),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.lock_outline, color: red),
                const SizedBox(height: 8),
                Text(
                  tr('التداول الحقيقي غير مفعّل', 'Live trading is disabled'),
                  style: const TextStyle(color: red, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 7),
                Text(
                  tr(
                    'لن يتم إرسال أوامر حقيقية قبل ربط API آمن واختبار التنفيذ وتفعيل التداول بموافقتك.',
                    'No real orders until secure API integration, execution tests and your explicit approval.',
                  ),
                  style: TextStyle(color: widget.muted, fontSize: 11, height: 1.5),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          Center(
            child: Text(
              'AI TRADE · BUILD 0.3.0',
              style: TextStyle(color: widget.muted, fontSize: 9, letterSpacing: 1.5),
            ),
          ),
        ],
      );

  static const widgetMuted = Color(0xFF8997B0);

  Widget _setting(IconData icon, String title, String sub, Widget trailing) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(
          children: [
            Icon(icon, color: cyan, size: 21),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: TextStyle(color: widget.text, fontSize: 12, fontWeight: FontWeight.bold)),
                  Text(sub, style: TextStyle(color: widget.muted, fontSize: 10)),
                ],
              ),
            ),
            trailing,
          ],
        ),
      );

  Widget _chart(bool compact) => _panel(
        child: Column(
          children: [
            Row(
              children: [
                Text(
                  'BTC / USDT',
                  style: TextStyle(color: widget.text, fontWeight: FontWeight.bold),
                ),
                const Spacer(),
                const Text(
                  '\$67,420',
                  style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18),
                ),
              ],
            ),
            const SizedBox(height: 5),
            const Row(
              children: [
                Text('+2.41%', style: TextStyle(color: green, fontSize: 11)),
                SizedBox(width: 6),
                Text('PREVIEW DATA', style: TextStyle(color: Colors.grey, fontSize: 9)),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: compact ? 150 : 235,
              child: AnimatedBuilder(
                animation: pulse,
                builder: (_, __) => CustomPaint(
                  painter: CandlePainter(pulse.value),
                  child: const SizedBox.expand(),
                ),
              ),
            ),
            Row(
              children: [
                _legend(green, 'BULLISH'),
                const SizedBox(width: 15),
                _legend(red, 'BEARISH'),
                const Spacer(),
                Text('RSI 58.4 · MACD +124', style: TextStyle(color: widget.muted, fontSize: 9)),
              ],
            ),
          ],
        ),
      );

  Widget _coin(String symbol, String pair, String name, String price, String change, Color color) =>
      _panel(
        padding: 13,
        child: Row(
          children: [
            Container(
              width: 39,
              height: 39,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: color.withOpacity(.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(symbol, style: TextStyle(color: color, fontSize: 21)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(pair, style: TextStyle(color: widget.text, fontWeight: FontWeight.bold, fontSize: 12)),
                  Text(name, style: TextStyle(color: widget.muted, fontSize: 10)),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(price, style: TextStyle(color: widget.text, fontWeight: FontWeight.bold)),
                Text(change, style: TextStyle(color: change.startsWith('+') ? green : red, fontSize: 10)),
              ],
            ),
          ],
        ),
      );

  Widget _agentRow(
      String domain, String name, String detail, Color color) {
    final control = agentControls[domain];
    final enabled = control is Map && control['enabled'] == true;

    return _panel(
      padding: 12,
      child: Row(
        children: [
          Container(
            width: 39,
            height: 39,
            decoration: BoxDecoration(
              color: color.withOpacity(.13),
              borderRadius: BorderRadius.circular(13),
            ),
            child: Icon(Icons.hub, color: color),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: TextStyle(
                  color: widget.text,
                  fontWeight: FontWeight.bold,
                  fontSize: 11,
                )),
                Text(detail, style: TextStyle(
                  color: widget.muted,
                  fontSize: 10,
                )),
                Text(
                  !apiOnline
                      ? tr('غير متصل', 'OFFLINE')
                      : enabled
                          ? tr('يقبل صفقات جديدة', 'ENABLED')
                          : tr('متوقف عن فتح صفقات', 'STOPPED'),
                  style: TextStyle(
                    color: !apiOnline ? red : enabled ? green : red,
                    fontSize: 9,
                  ),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: !apiOnline || apiBusy
                ? null
                : () => _setAgent(domain, !enabled),
            child: Text(
              enabled
                  ? tr('إيقاف', 'STOP')
                  : tr('استئناف', 'RESUME'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _activityCard() => _panel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(tr('آخر النشاطات', 'RECENT ACTIVITY'), style: TextStyle(color: widget.text, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            _legend(cyan, tr('واجهة النظام جاهزة للعرض', 'Dashboard preview ready')),
            const SizedBox(height: 10),
            _legend(green, tr('لا توجد صفقات مفتوحة', 'No open trades')),
          ],
        ),
      );

  Widget _heading(String title, String sub, IconData icon) => Row(
        children: [
          Icon(icon, color: cyan, size: 19),
          const SizedBox(width: 7),
          Expanded(
            child: Text(title, style: TextStyle(color: widget.text, fontSize: 15, fontWeight: FontWeight.w800)),
          ),
          Text(sub, style: TextStyle(color: widget.muted, fontSize: 8, letterSpacing: 1)),
        ],
      );

  Widget _pageHeading(String title, String sub) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: TextStyle(color: widget.text, fontSize: 21, fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          Text(sub, style: TextStyle(color: widget.muted, fontSize: 9, letterSpacing: 1.5)),
        ],
      );

  Widget _panel({required Widget child, Color? border, double padding = 15}) =>
      Container(
        padding: EdgeInsets.all(padding),
        decoration: BoxDecoration(
          color: widget.panel,
          borderRadius: BorderRadius.circular(21),
          border: Border.all(color: border ?? widget.muted.withOpacity(.13)),
          boxShadow: widget.dark
              ? [BoxShadow(color: Colors.black.withOpacity(.12), blurRadius: 16, offset: const Offset(0, 6))]
              : [],
        ),
        child: child,
      );

  Widget _pill(String label, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withOpacity(.12),
          border: Border.all(color: color.withOpacity(.4)),
          borderRadius: BorderRadius.circular(30),
        ),
        child: Text(label, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.bold)),
      );

  Widget _metric(String title, String value, Color color) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: TextStyle(color: widget.muted, fontSize: 9)),
            const SizedBox(height: 5),
            Text(value, style: TextStyle(color: color, fontSize: 15, fontWeight: FontWeight.w900)),
          ],
        ),
      );

  Widget _legend(Color color, String label) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              boxShadow: [BoxShadow(color: color.withOpacity(.45), blurRadius: 6)],
            ),
          ),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(color: widget.muted, fontSize: 9)),
        ],
      );

  Widget _tradeButton(String label, Color color, VoidCallback action) =>
      FilledButton(
        onPressed: action,
        style: FilledButton.styleFrom(
          backgroundColor: color.withOpacity(.15),
          foregroundColor: color,
          padding: const EdgeInsets.symmetric(vertical: 13),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
        ),
        child: Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
      );

  Widget _bottomBar(List<String> titles) {
    const icons = [
      Icons.grid_view_rounded,
      Icons.hub_rounded,
      Icons.candlestick_chart_rounded,
      Icons.account_balance_wallet_rounded,
      Icons.settings_rounded,
    ];
    return Container(
      padding: const EdgeInsets.fromLTRB(7, 8, 7, 17),
      decoration: BoxDecoration(
        color: widget.panel,
        border: Border(top: BorderSide(color: widget.muted.withOpacity(.15))),
      ),
      child: Row(
        children: List.generate(5, (i) {
          final selected = page == i;
          return Expanded(
            child: InkWell(
              onTap: () => setState(() => page = i),
              borderRadius: BorderRadius.circular(14),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                decoration: BoxDecoration(
                  color: selected ? cyan.withOpacity(.12) : Colors.transparent,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icons[i], color: selected ? cyan : widget.muted, size: 21),
                    const SizedBox(height: 4),
                    Text(
                      titles[i],
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: selected ? cyan : widget.muted,
                        fontSize: 9,
                        fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ),
    );
}

class GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()..color = cyan.withOpacity(.055)..strokeWidth = 1;
    for (double x = 0; x < size.width; x += 30) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), p);
    }
    for (double y = 0; y < size.height; y += 30) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), p);
    }
  }
  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class OrbPainter extends CustomPainter {
  final double t;
  OrbPainter(this.t);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width * .5, size.height * .5);
    final r = size.width * .27;
    canvas.drawCircle(
      center,
      r * 1.8,
      Paint()
        ..shader = RadialGradient(
          colors: [cyan.withOpacity(.28), blue.withOpacity(.06), Colors.transparent],
        ).createShader(Rect.fromCircle(center: center, radius: r * 1.8)),
    );
    canvas.drawCircle(
      center,
      r,
      Paint()
        ..shader = const RadialGradient(
          colors: [Color(0xFF8CFFF4), Color(0xFF00AFA5), Color(0xFF112044)],
          center: Alignment(-.4, -.4),
        ).createShader(Rect.fromCircle(center: center, radius: r)),
    );
    for (int i = 0; i < 3; i++) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate(t * math.pi * 2 + i * math.pi / 3);
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: r * 3, height: r * .85),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4
          ..color = [cyan, blue, violet][i].withOpacity(.8),
      );
      canvas.restore();
    }
    for (int i = 0; i < 8; i++) {
      final a = t * math.pi * 2 + i * math.pi / 4;
      canvas.drawCircle(
        Offset(center.dx + math.cos(a) * r * 1.5, center.dy + math.sin(a) * r * .7),
        3,
        Paint()..color = i.isEven ? cyan : violet,
      );
    }
  }

  @override
  bool shouldRepaint(covariant OrbPainter old) => old.t != t;
}

class NetworkPainter extends CustomPainter {
  final double t;
  NetworkPainter(this.t);

  @override
  void paint(Canvas canvas, Size s) {
    final center = Offset(s.width * .5, s.height * .49);
    final colors = [cyan, blue, violet];
    final nodes = [
      Offset(s.width * .5, s.height * .17),
      Offset(s.width * .22, s.height * .72),
      Offset(s.width * .78, s.height * .72),
    ];
    for (int i = 0; i < 3; i++) {
      canvas.drawLine(
        center,
        nodes[i],
        Paint()..color = colors[i].withOpacity(.5)..strokeWidth = 1.5,
      );
      canvas.drawCircle(nodes[i], 37, Paint()..color = colors[i].withOpacity(.09));
      canvas.drawCircle(nodes[i], 27, Paint()..color = const Color(0xFF142239));
      canvas.drawCircle(
        nodes[i],
        27,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = colors[i],
      );
      canvas.drawCircle(nodes[i], 6, Paint()..color = colors[i]);
      final f = (t + i * .3) % 1;
      canvas.drawCircle(
        Offset.lerp(center, nodes[i], f)!,
        3,
        Paint()..color = colors[i],
      );
      final label = TextPainter(
        text: TextSpan(
          text: ['FUTURES', 'SPOT', 'ALPHA'][i],
          style: TextStyle(color: colors[i], fontSize: 9, fontWeight: FontWeight.bold),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      label.paint(canvas, Offset(nodes[i].dx - label.width / 2, nodes[i].dy + 34));
    }
    canvas.drawCircle(
      center,
      39,
      Paint()
        ..shader = RadialGradient(
          colors: [cyan.withOpacity(.6), blue.withOpacity(.15), Colors.transparent],
        ).createShader(Rect.fromCircle(center: center, radius: 39)),
    );
    canvas.drawCircle(
      center,
      22,
      Paint()
        ..shader = const RadialGradient(
          colors: [Color(0xFF7FFFF0), Color(0xFF007C9D), Color(0xFF111A35)],
        ).createShader(Rect.fromCircle(center: center, radius: 22)),
    );
    final tp = TextPainter(
      text: const TextSpan(
        text: 'AI',
        style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w900),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(center.dx - tp.width / 2, center.dy - tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant NetworkPainter old) => old.t != t;
}

class CandlePainter extends CustomPainter {
  final double t;
  CandlePainter(this.t);

  @override
  void paint(Canvas canvas, Size s) {
    final grid = Paint()..color = Colors.white.withOpacity(.06)..strokeWidth = 1;
    for (int i = 0; i < 5; i++) {
      final y = s.height * i / 4;
      canvas.drawLine(Offset(0, y), Offset(s.width, y), grid);
    }
    const count = 36;
    final step = s.width / count;
    for (int i = 0; i < count; i++) {
      final x = i * step + step / 2;
      final wave = math.sin(i * .65 + t * 1.2) * s.height * .11 +
          math.sin(i * .19) * s.height * .13;
      final open = s.height * .53 - wave;
      final close = open + math.sin(i * 1.1 + t * .3) * s.height * .13;
      final high = math.min(open, close) - 5 - (i % 4) * 2;
      final low = math.max(open, close) + 5 + (i % 3) * 2;
      final color = close < open ? green : red;
      final p = Paint()..color = color..strokeWidth = 1.4;
      canvas.drawLine(Offset(x, high), Offset(x, low), p);
      canvas.drawRect(
        Rect.fromLTRB(
          x - step * .28,
          math.min(open, close),
          x + step * .28,
          math.max(open, close) + 1,
        ),
        Paint()..color = color.withOpacity(.9),
      );
    }
    final y = s.height * .3;
    for (double x = 0; x < s.width - 70; x += 9) {
      canvas.drawLine(
        Offset(x, y),
        Offset(x + 4, y),
        Paint()..color = cyan.withOpacity(.8)..strokeWidth = 1,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CandlePainter old) => old.t != t;
}

class DonutPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size s) {
    final rect = Rect.fromLTWH(8, 8, s.width - 16, s.height - 16);
    canvas.drawArc(
      rect,
      -math.pi / 2,
      math.pi * 2 - .08,
      false,
      Paint()
        ..color = cyan
        ..style = PaintingStyle.stroke
        ..strokeWidth = 13
        ..strokeCap = StrokeCap.round,
    );
    final tp = TextPainter(
      text: const TextSpan(
        text: '100%',
        style: TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w900),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset((s.width - tp.width) / 2, (s.height - tp.height) / 2));
  }

  @override
  bool shouldRepaint(covariant DonutPainter old) => false;
}
