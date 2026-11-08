import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'screens/performance_screen.dart';
import 'screens/pro_chart_screen.dart';
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
  String mode = 'DEMO';

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
  Map<String, dynamic> demoData = {};
  Map<String, dynamic> agentControls = {};
  final Set<String> closingPositionIds = {};
  Timer? _refreshTimer;
  final Map<String, List<Map<String, double>>> _marketCandles = {};
  final Map<String, List<String>> _marketSymbols = {};
  final Map<String, String> _selectedSymbols = {
    'futures': 'BTCUSDT',
    'spot': 'BTCUSDT',
    'alpha': '',
  };
  final Map<String, String> _selectedIntervals = {
    'futures': '5m',
    'spot': '5m',
    'alpha': '5m',
  };
  final Set<String> _marketLoading = {};
  bool _marketRefreshing = false;
  late final AnimationController pulse = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 9),
  )..repeat();

  bool get en => widget.english;
  String tr(String ar, String eng) => en ? eng : ar;

  @override
  void initState() {
    super.initState();
    () async {
      await _refreshStatus();
      if (!mounted) return;
      await _refreshMarketData(loadSymbols: true);
    }();
    _refreshTimer = Timer.periodic(const Duration(seconds: 15), (_) async {
      if (!mounted) return;
      await _refreshStatus();
      if (!mounted) return;
      await _refreshMarketData();
    });
  }

  Future<void> _refreshStatus() async {
    if (apiBusy) return;
    setState(() => apiBusy = true);
    try {
      final data = await ApiService.status();
      if (!mounted) return;
      _applyStatus(data);
      setState(() => apiOnline = true);
    } catch (_) {
      if (mounted) setState(() => apiOnline = false);
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
  }

  List<Map<String, double>> _normalizeCandles(dynamic raw) {
    if (raw is! List) return [];
    final result = <Map<String, double>>[];
    for (final item in raw) {
      try {
        if (item is Map) {
          double n(dynamic v) => double.tryParse('$v') ?? 0;
          final candle = {
            'open': n(item['open'] ?? item['o']),
            'high': n(item['high'] ?? item['h']),
            'low': n(item['low'] ?? item['l']),
            'close': n(item['close'] ?? item['c']),
          };
          if (candle['high']! > 0 && candle['low']! > 0) {
            result.add(candle);
          }
        } else if (item is List && item.length >= 5) {
          double n(dynamic v) => double.tryParse('$v') ?? 0;
          final candle = {
            'open': n(item[1]),
            'high': n(item[2]),
            'low': n(item[3]),
            'close': n(item[4]),
          };
          if (candle['high']! > 0 && candle['low']! > 0) {
            result.add(candle);
          }
        }
      } catch (_) {}
    }
    return result;
  }

  Future<void> _loadMarketSymbols(String market) async {
    try {
      final result = await ApiService.marketSymbols(market);
      if (!mounted) return;
      dynamic raw = result['symbols'] ?? result['data'] ?? result['items'];
      if (raw is Map) {
        raw = raw['symbols'] ?? raw['items'] ?? raw['data'];
      }
      final symbols = <String>[];
      if (raw is List) {
        for (final item in raw) {
          final value = item is Map
              ? (item['symbol'] ?? item['s'] ?? item['pair'])
              : item;
          if (value != null && '$value'.isNotEmpty) {
            symbols.add('$value');
          }
        }
      }
      if (symbols.isNotEmpty) {
        setState(() {
          _marketSymbols[market] = symbols.toSet().toList()..sort();
          if (!_marketSymbols[market]!.contains(_selectedSymbols[market])) {
            _selectedSymbols[market] = _marketSymbols[market]!.first;
          }
        });
      }
    } catch (_) {}
  }

  Future<void> _loadMarketCandles(String market) async {
    final symbol = _selectedSymbols[market] ?? '';
    final interval = _selectedIntervals[market] ?? '5m';
    if (symbol.isEmpty) return;
    final key = '$market:$symbol:$interval';
    if (_marketLoading.contains(key)) return;
    _marketLoading.add(key);
    try {
      final result = await ApiService.marketCandles(
        market: market,
        symbol: symbol,
        interval: interval,
        limit: 100,
      );
      if (!mounted) return;
      final raw = result['candles'] ??
          result['klines'] ??
          result['data'] ??
          result['items'];
      final candles = _normalizeCandles(raw);
      if (candles.isNotEmpty) {
        setState(() => _marketCandles[key] = candles);
      }
    } catch (_) {
      // Keep the last successfully received market data.
    } finally {
      _marketLoading.remove(key);
    }
  }

  Future<void> _loadPositionCandles(String market, String symbol) async {
    if (symbol.isEmpty) return;
    final key = '$market:$symbol:5m';
    if (_marketLoading.contains(key)) return;
    _marketLoading.add(key);
    try {
      final result = await ApiService.marketCandles(
        market: market,
        symbol: symbol,
        interval: '5m',
        limit: 80,
      );
      if (!mounted) return;
      final raw = result['candles'] ??
          result['klines'] ??
          result['data'] ??
          result['items'];
      final parsed = _normalizeCandles(raw);
      if (parsed.isNotEmpty) {
        setState(() => _marketCandles[key] = parsed);
      }
    } catch (_) {
      // Keep the last successfully received candles.
    } finally {
      _marketLoading.remove(key);
    }
  }

  Future<void> _refreshMarketData({bool loadSymbols = false}) async {
    if (_marketRefreshing) return;
    _marketRefreshing = true;
    try {
      for (final market in ['futures', 'spot', 'alpha']) {
        if (loadSymbols || !(_marketSymbols[market]?.isNotEmpty ?? false)) {
          await _loadMarketSymbols(market);
        }
        await _loadMarketCandles(market);
      }

      final rawPositions = demoData['open_positions'];
      if (rawPositions is List) {
        final refreshed = <String>{};
        for (final item in rawPositions) {
          if (item is! Map) continue;
          final position = Map<String, dynamic>.from(item);
          final domain = '${position['domain'] ?? position['market_type'] ?? 'spot'}'.toLowerCase();
          final market = domain.contains('future')
              ? 'futures'
              : domain.contains('alpha')
                  ? 'alpha'
                  : 'spot';
          final symbol = '${position['symbol'] ?? ''}';
          final key = '$market:$symbol:5m';
          if (symbol.isNotEmpty && refreshed.add(key)) {
            await _loadPositionCandles(market, symbol);
          }
        }
      }
    } finally {
      _marketRefreshing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _chooseMarketSymbol(String market) async {
    if (!(_marketSymbols[market]?.isNotEmpty ?? false)) {
      await _loadMarketSymbols(market);
    }
    if (!mounted) return;
    final symbols = _marketSymbols[market] ?? [];
    if (symbols.isEmpty) {
      notify(tr('تعذر تحميل أزواج هذا السوق', 'Could not load market pairs'));
      return;
    }
    final selected = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: widget.panel,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: SizedBox(
          height: MediaQuery.of(ctx).size.height * .72,
          child: ListView(
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  tr('اختر زوج التداول', 'Select trading pair'),
                  style: TextStyle(
                    color: widget.text,
                    fontWeight: FontWeight.bold,
                    fontSize: 17,
                  ),
                ),
              ),
              ...symbols.map((symbol) => ListTile(
                title: Text(symbol, style: TextStyle(color: widget.text)),
                trailing: symbol == _selectedSymbols[market]
                    ? const Icon(Icons.check_circle, color: cyan)
                    : null,
                onTap: () => Navigator.pop(ctx, symbol),
              )),
            ],
          ),
        ),
      ),
    );
    if (selected == null || !mounted) return;
    setState(() => _selectedSymbols[market] = selected);
    await _loadMarketCandles(market);
  }

  Widget _marketPanel(String market, String title, Color accent) {
    final symbol = _selectedSymbols[market] ?? '';
    final interval = _selectedIntervals[market] ?? '5m';
    final key = '$market:$symbol:$interval';
    final candles = _marketCandles[key] ?? [];
    final last = candles.isNotEmpty ? candles.last['close']! : 0.0;
    final intervals = market == 'alpha'
        ? ['5m', '15m', '1h']
        : ['5m', '15m', '1h', '4h'];

    return _panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              width: 8,
              height: 28,
              decoration: BoxDecoration(
                color: accent,
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Text(title,
                style: TextStyle(
                  color: widget.text,
                  fontWeight: FontWeight.w900,
                  fontSize: 15,
                ),
              ),
            ),
            Text(
              market.toUpperCase(),
              style: TextStyle(color: accent, fontSize: 9,
                fontWeight: FontWeight.bold),
            ),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _chooseMarketSymbol(market),
                icon: const Icon(Icons.swap_horiz, size: 17),
                label: Text(symbol.isEmpty ? 'Select pair' : symbol,
                  overflow: TextOverflow.ellipsis),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              onPressed: () => _loadMarketCandles(market),
              icon: const Icon(Icons.refresh, color: cyan),
            ),
          ]),
          Row(
            children: intervals.map((tf) {
              final active = interval == tf;
              return Padding(
                padding: const EdgeInsetsDirectional.only(end: 7),
                child: ChoiceChip(
                  label: Text(tf),
                  selected: active,
                  onSelected: (_) {
                    setState(() => _selectedIntervals[market] = tf);
                    _loadMarketCandles(market);
                  },
                  selectedColor: accent.withOpacity(.22),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: Text(
                last > 0 ? last.toStringAsFixed(6) : '—',
                style: TextStyle(
                  color: widget.text,
                  fontWeight: FontWeight.w900,
                  fontSize: 18,
                ),
              ),
            ),
            Text(
              candles.isEmpty
                  ? tr('بانتظار بيانات السوق', 'Waiting for market data')
                  : tr('بيانات Binance', 'Binance market data'),
              style: TextStyle(color: widget.muted, fontSize: 10),
            ),
          ]),
          const SizedBox(height: 8),
          SizedBox(
            height: 190,
            child: candles.isEmpty
                ? Center(
                    child: Text(
                      tr('لا توجد شموع متاحة حالياً', 'No candles available'),
                      style: TextStyle(color: widget.muted),
                    ),
                  )
                : CustomPaint(
                    painter: LiveCandlePainter(candles),
                    child: const SizedBox.expand(),
                  ),
          ),
        ],
      ),
    );
  }

  Future<void> _closeDemoPosition(Map<String, dynamic> position) async {
    final id = '${position['id'] ?? position['position_id'] ?? position['trade_id'] ?? ''}';
    if (id.isEmpty || closingPositionIds.contains(id)) return;

    final isDemo = widget.mode.toUpperCase() == 'DEMO';
    if (!isDemo) return;
    if (!isDemo) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: widget.panel,
        title: Text(tr('تأكيد إغلاق الصفقة', 'Confirm position close')),
        content: Text(
          tr(
            'سيتم إغلاق ${position['symbol'] ?? ''} في وضع DEMO. هذا الإجراء خاص بهذا المركز فقط.',
            'This will close ${position['symbol'] ?? ''} in DEMO mode. Only this position will be affected.',
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
      final result = await ApiService.closeDemoTrade(positionId: id);

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
    final demo = data['demo'];
    final controls = data['controls'];
    apiOnline = true;
    demoData = demo is Map
        ? Map<String, dynamic>.from(demo)
        : <String, dynamic>{};
    final raw = demoData['open_positions'] ??
        demoData['positions'] ??
        demoData['items'];
    final positions = raw is List
        ? raw.whereType<Map>().map((item) {
            final position = Map<String, dynamic>.from(item);
            position['id'] = position['id'] ??
                position['position_id'] ??
                position['trade_id'] ??
                '';
            return position;
          }).where((item) => item['id'].toString().isNotEmpty).toList()
        : <Map<String, dynamic>>[];
    demoData['open_positions'] = positions;
    agentControls = controls is Map
        ? Map<String, dynamic>.from(controls)
        : <String, dynamic>{};
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
    _refreshTimer?.cancel();
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
          _chart(true),
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

  Future<void> _depositDemoBalance() async {
    final amountController = TextEditingController();
    final amount = await showDialog<double>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: widget.panel,
        title: Text(tr('إضافة رصيد إلى DEMO', 'Add DEMO balance')),
        content: TextField(
          controller: amountController,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: tr('المبلغ بالدولار', 'Amount in USD'),
            prefixText: r'$ ',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(tr('إلغاء', 'Cancel')),
          ),
          FilledButton(
            onPressed: () {
              final value = double.tryParse(amountController.text.trim());
              if (value != null && value.isFinite && value > 0) {
                Navigator.pop(ctx, value);
              }
            },
            child: Text(tr('إضافة', 'Add')),
          ),
        ],
      ),
    );
    amountController.dispose();
    if (amount == null || !mounted) return;

    setState(() => apiBusy = true);
    var success = false;
    try {
      final result = await ApiService.depositDemoBalance(amount);
      if (!mounted) return;
      success = result['success'] == true;
      notify(success
          ? tr('تمت إضافة الرصيد الافتراضي بنجاح.', 'DEMO balance added successfully.')
          : '${tr('تعذر إضافة الرصيد: ', 'Deposit failed: ')}${result['reason'] ?? result['error'] ?? 'Unknown error'}');
    } catch (error) {
      if (mounted) {
        notify('${tr('خطأ أثناء الإيداع: ', 'Deposit error: ')}$error');
      }
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
    if (success && mounted) await _refreshStatus();
  }


  Widget _portfolioCard() {
    final rawSummary = demoData['account_summary'];
    final summary = rawSummary is Map
        ? Map<String, dynamic>.from(rawSummary)
        : <String, dynamic>{};

    String money(List<String> keys) {
      for (final key in keys) {
        final value = summary[key] ?? demoData[key];
        final number = double.tryParse('$value');
        if (number != null) {
          return '\$${number.toStringAsFixed(2)}';
        }
      }
      return '—';
    }

    final equity = money(['equity', 'total_equity']);
    final available = money(['available_balance', 'available']);
    final wallet = money(['wallet_balance', 'balance']);
    final margin = money(['locked_margin', 'used_margin']);
    final unrealized = money(['unrealized_pnl', 'unrealized_profit']);
    final realized = money(['realized_pnl', 'realized_profit']);
    final fees = money(['total_fees', 'fees']);
    final openCount = demoData['open_count'] ??
        (demoData['open_positions'] is List
            ? (demoData['open_positions'] as List).length
            : 0);
    final totalTrades = demoData['total_trades'] ?? 0;

    return _panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                tr('حساب DEMO', 'DEMO ACCOUNT'),
                style: TextStyle(color: widget.muted, fontSize: 11),
              ),
              const Spacer(),
              _pill(apiOnline ? 'DEMO' : tr('غير متصل', 'OFFLINE'),
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
            apiOnline ? equity : '—',
            style: TextStyle(
              color: widget.text,
              fontSize: 34,
              fontWeight: FontWeight.w900,
            ),
          ),
          Text(
            tr('إجمالي قيمة الحساب', 'TOTAL ACCOUNT EQUITY'),
            style: TextStyle(color: widget.muted, fontSize: 10),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              _metric(tr('المتاح', 'AVAILABLE'), apiOnline ? available : '—', widget.text),
              _metric(tr('المحفظة', 'WALLET'), apiOnline ? wallet : '—', widget.text),
              _metric(tr('الهامش المحجوز', 'LOCKED MARGIN'), apiOnline ? margin : '—', widget.text),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _metric(tr('ربح عائم', 'UNREALIZED PNL'), apiOnline ? unrealized : '—', widget.text),
              _metric(tr('ربح محقق', 'REALIZED PNL'), apiOnline ? realized : '—', widget.text),
              _metric(tr('الرسوم', 'FEES'), apiOnline ? fees : '—', widget.text),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _metric(tr('المراكز المفتوحة', 'OPEN POSITIONS'),
                  apiOnline ? '$openCount' : '—', widget.text),
              _metric(tr('إجمالي الصفقات', 'TOTAL TRADES'),
                  apiOnline ? '$totalTrades' : '—', widget.text),
            ],
          ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: apiBusy || !apiOnline ? null : _depositDemoBalance,
                icon: const Icon(Icons.add_circle_outline, size: 18),
                label: Text(tr('إضافة رصيد افتراضي', 'Add DEMO funds')),
              ),
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
                  'سيتم تنفيذ محاكاة صفقة $side على BTCUSDT داخل محرك DEMO المحلي، باستخدام أسعار Binance الحقيقية، مع مخاطرة 0.5% ورافعة 1x. لن يتم إرسال أي أوامر إلى Binance.',
                  'A $side BTCUSDT trade will be simulated locally in the DEMO engine using live Binance market prices, with 0.5% risk and 1x leverage. No orders will be sent to Binance.',
                )
              : tr(
                  'التداول الحقيقي غير متاح؛ وضع LIVE مقفل من الخادم.',
                  'Live trading is unavailable and securely locked by the backend.',
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
                        'التداول الحقيقي غير متاح؛ وضع LIVE مقفل من الخادم.',
                        'Live trading is unavailable and securely locked by the backend.',
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

                      final success = result['approved'] == true ||
                          result['success'] == true;

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

  void _openProChart() {
    final raw = demoData['open_positions'];
    final positions = raw is List
        ? raw
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList()
        : <Map<String, dynamic>>[];
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ProChartScreen(
          english: en,
          bg: widget.bg,
          panel: widget.panel,
          text: widget.text,
          muted: widget.muted,
          positions: positions,
        ),
      ),
    );
  }

  void _openPerformance() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => PerformanceScreen(
          english: en,
          bg: widget.bg,
          panel: widget.panel,
          text: widget.text,
          muted: widget.muted,
        ),
      ),
    );
  }

  Widget _proTools() => Row(
        children: [
          Expanded(
            child: FilledButton.icon(
              onPressed: _openProChart,
              icon: const Icon(Icons.candlestick_chart, size: 18),
              label: Text(tr('تشارت احترافي', 'Pro Chart')),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton.icon(
              onPressed: _openPerformance,
              icon: const Icon(Icons.insights, size: 18),
              label: Text(tr('الأداء والآلي', 'Autopilot')),
            ),
          ),
        ],
      );

  Widget _markets() => ListView(
    padding: const EdgeInsets.all(15),
    children: [
      _pageHeading(
        tr('مركز الأسواق', 'MARKET INTELLIGENCE'),
        'LIVE BINANCE DATA',
      ),
      const SizedBox(height: 12),
      _proTools(),
      const SizedBox(height: 12),
      _marketPanel('futures', tr('العقود الآجلة', 'FUTURES'), cyan),
      const SizedBox(height: 13),
      _marketPanel('spot', tr('السوق الفوري', 'SPOT'), blue),
      const SizedBox(height: 13),
      _marketPanel('alpha', 'ALPHA', violet),
    ],
  );

  Widget _positionLiveChart(Map<String, dynamic> position) {
    final domain = '${position['domain'] ?? 'spot'}'.toLowerCase();
    final market = domain.contains('future')
        ? 'futures'
        : domain.contains('alpha')
            ? 'alpha'
            : 'spot';
    final symbol = '${position['symbol'] ?? ''}';
    final key = '$market:$symbol:5m';
    final candles = _marketCandles[key] ?? [];
    final current = candles.isNotEmpty ? candles.last['close']! : 0.0;
    final entry = double.tryParse('${position['entry_price'] ?? ''}') ?? 0;
    final stop = double.tryParse('${position['stop_loss'] ?? ''}') ?? 0;
    final target = double.tryParse('${position['take_profit'] ?? ''}') ?? 0;

    if (symbol.isNotEmpty && candles.isEmpty && !_marketLoading.contains(key)) {
      Future.microtask(() => _loadPositionCandles(market, symbol));
    }

    final direction = '${position['direction'] ?? 'LONG'}'.toUpperCase();
    final qty = double.tryParse(
      '${position['remaining_quantity'] ?? position['quantity'] ?? ''}',
    ) ?? 0;
    final pnl = current > 0 && entry > 0
        ? (direction == 'SHORT' ? entry - current : current - entry) * qty
        : null;

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: widget.bg.withOpacity(.55),
        borderRadius: BorderRadius.circular(13),
        border: Border.all(color: cyan.withOpacity(.16)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(
                current > 0
                    ? '${tr('السعر الحالي', 'CURRENT PRICE')}: ${current.toStringAsFixed(6)}'
                    : tr('بانتظار السعر الحي', 'Waiting for live price'),
                style: TextStyle(color: widget.text, fontSize: 11,
                  fontWeight: FontWeight.bold),
              ),
            ),
            if (pnl != null)
              Text(
                '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(4)} USDT',
                style: TextStyle(
                  color: pnl >= 0 ? green : red,
                  fontWeight: FontWeight.bold,
                  fontSize: 11,
                ),
              ),
          ]),
          const SizedBox(height: 8),
          SizedBox(
            height: 125,
            child: candles.isEmpty
                ? Center(
                    child: Text(
                      tr('يتم تحميل التشارت...', 'Loading position chart...'),
                      style: TextStyle(color: widget.muted, fontSize: 10),
                    ),
                  )
                : CustomPaint(
                    painter: LiveCandlePainter(
                      candles,
                      entry: entry,
                      stop: stop,
                      target: target,
                    ),
                    child: const SizedBox.expand(),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _openPositionsSection() {
    final raw = demoData['open_positions'];
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
                    _positionLiveChart(position),
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
                            : () => _closeDemoPosition(position),
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
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(
          children: [
            Container(
              width: 39,
              height: 39,
              decoration: BoxDecoration(
                color: cyan.withOpacity(widget.dark ? .13 : .09),
                borderRadius: BorderRadius.circular(13),
                border: Border.all(color: cyan.withOpacity(.16)),
              ),
              child: Icon(icon, color: cyan, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: TextStyle(color: widget.text, fontSize: 12, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 3),
                  Text(sub, style: TextStyle(color: widget.muted, fontSize: 10)),
                ],
              ),
            ),
            trailing,
          ],
        ),
      );

  Future<void> _submitHomeChartToAgent(String symbol, String timeframe) async {
    if (!apiOnline || apiBusy) {
      notify(tr('اتصل بالخادم أولاً لإرسال الفرصة.', 'Connect to the backend before submitting the chart.'));
      return;
    }
    setState(() => apiBusy = true);
    try {
      final result = await ApiService.submitChartSignal(
        domain: 'futures',
        symbol: symbol,
        timeframe: timeframe,
      );
      if (!mounted) return;
      final signal = result['signal'] is Map
          ? Map<String, dynamic>.from(result['signal'] as Map)
          : <String, dynamic>{};
      final plan = result['trade_plan'] is Map
          ? Map<String, dynamic>.from(result['trade_plan'] as Map)
          : <String, dynamic>{};
      final decision = result['decision'] ?? result['reason'] ?? 'No decision';
      notify(
        '${decision} · ${signal['direction'] ?? 'WAIT'} · ${tr('الثقة', 'Confidence')} ${signal['confidence'] ?? 0}%'
        '${plan['success'] == true ? ' · R/R ${plan['reward_risk']}' : ''}'
        ' · ${result['opened'] == true ? tr('تم فتح صفقة DEMO', 'DEMO position opened') : tr('لم تُفتح صفقة', 'No trade opened')}',
      );
      if (result['opened'] == true) await _refreshStatus();
    } catch (error) {
      if (mounted) notify('${tr('تعذر إرسال الفرصة: ', 'Submit failed: ')}$error');
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
  }

  Widget _chart(bool compact) {
    final symbol = _selectedSymbols['futures'] ?? 'BTCUSDT';
    final interval = _selectedIntervals['futures'] ?? '5m';
    final key = 'futures:$symbol:$interval';
    final candles = _marketCandles[key] ?? [];
    final last = candles.isNotEmpty ? candles.last['close']! : 0.0;
    final first = candles.isNotEmpty ? candles.first['open']! : 0.0;
    final change = first > 0 ? ((last - first) / first) * 100 : null;

    return _panel(
      child: Column(
        children: [
          Row(
            children: [
              Text(
                symbol,
                style: TextStyle(color: widget.text, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              Text(
                last > 0 ? last.toStringAsFixed(2) : '—',
                style: TextStyle(
                  color: widget.text,
                  fontWeight: FontWeight.w900,
                  fontSize: 18,
                ),
              ),
            ],
          ),
          const SizedBox(height: 5),
          Row(
            children: [
              if (change != null)
                Text(
                  '${change >= 0 ? '+' : ''}${change.toStringAsFixed(2)}%',
                  style: TextStyle(
                    color: change >= 0 ? green : red,
                    fontSize: 11,
                  ),
                ),
              const SizedBox(width: 8),
              Text(
                apiOnline && candles.isNotEmpty ? 'BINANCE LIVE' : 'DATA UNAVAILABLE',
                style: TextStyle(
                  color: apiOnline && candles.isNotEmpty ? green : red,
                  fontSize: 9,
                ),
              ),
              const Spacer(),
              Text(
                '$interval · ${candles.length} ${tr('شمعة', 'candles')}',
                style: TextStyle(color: widget.muted, fontSize: 9),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: compact ? 150 : 235,
            child: candles.isEmpty
                ? Center(
                    child: Text(
                      tr('بانتظار بيانات Binance الحقيقية', 'Waiting for live Binance candles'),
                      style: TextStyle(color: widget.muted, fontSize: 11),
                    ),
                  )
                : CustomPaint(
                    painter: LiveCandlePainter(candles),
                    child: const SizedBox.expand(),
                  ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _legend(green, 'BULLISH'),
              const SizedBox(width: 15),
              _legend(red, 'BEARISH'),
              const Spacer(),
              Text(
                tr('المصدر: Binance REST', 'Source: Binance REST'),
                style: TextStyle(color: widget.muted, fontSize: 9),
              ),
            ],
          ),
          if (compact) ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: apiBusy ? null : () => _submitHomeChartToAgent(symbol, interval),
                icon: const Icon(Icons.psychology_alt, size: 17),
                label: Text(tr('إرسال للوكيل', 'SEND TO AGENT')),
              ),
            ),
          ],
        ],
      ),
    );
  }

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
          color: widget.dark
              ? widget.panel.withOpacity(.82)
              : Colors.white.withOpacity(.88),
          borderRadius: BorderRadius.circular(21),
          border: Border.all(
            color: border ?? (widget.dark
                ? Colors.white.withOpacity(.10)
                : Colors.white.withOpacity(.85)),
          ),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: widget.dark
                ? [
                    const Color(0xFF18263B).withOpacity(.92),
                    const Color(0xFF0D1728).withOpacity(.96),
                  ]
                : [
                    Colors.white.withOpacity(.96),
                    const Color(0xFFEAF1FA).withOpacity(.88),
                  ],
          ),
          boxShadow: [
            BoxShadow(
              color: widget.dark
                  ? Colors.black.withOpacity(.22)
                  : const Color(0xFF8295AD).withOpacity(.13),
              blurRadius: 22,
              offset: const Offset(0, 8),
            ),
            if (widget.dark)
              BoxShadow(
                color: cyan.withOpacity(.035),
                blurRadius: 18,
                spreadRadius: -5,
              ),
          ],
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

class LiveCandlePainter extends CustomPainter {
  final List<Map<String, double>> candles;
  final double entry;
  final double stop;
  final double target;

  LiveCandlePainter(
    this.candles, {
    this.entry = 0,
    this.stop = 0,
    this.target = 0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty || size.width <= 0 || size.height <= 0) return;

    final visible = candles.length > 70
        ? candles.sublist(candles.length - 70)
        : candles;
    var minPrice = visible.map((c) => c['low']!).reduce(math.min);
    var maxPrice = visible.map((c) => c['high']!).reduce(math.max);
    for (final level in [entry, stop, target]) {
      if (level > 0) {
        minPrice = math.min(minPrice, level);
        maxPrice = math.max(maxPrice, level);
      }
    }
    final spread = maxPrice - minPrice;
    if (spread <= 0) return;
    final pad = spread * .08;
    minPrice -= pad;
    maxPrice += pad;
    final range = maxPrice - minPrice;
    double y(double price) =>
        size.height - ((price - minPrice) / range) * size.height;

    final grid = Paint()
      ..color = Colors.white.withOpacity(.07)
      ..strokeWidth = 1;
    for (int i = 0; i < 5; i++) {
      final gy = size.height * i / 4;
      canvas.drawLine(Offset(0, gy), Offset(size.width, gy), grid);
    }

    final step = size.width / visible.length;
    final bodyWidth = math.max(2.0, step * .58);
    for (int i = 0; i < visible.length; i++) {
      final c = visible[i];
      final open = c['open']!;
      final close = c['close']!;
      final high = c['high']!;
      final low = c['low']!;
      final color = close >= open ? green : red;
      final x = step * i + step / 2;
      final paint = Paint()
        ..color = color
        ..strokeWidth = 1.2;
      canvas.drawLine(Offset(x, y(high)), Offset(x, y(low)), paint);
      final top = math.min(y(open), y(close));
      final bottom = math.max(y(open), y(close));
      canvas.drawRect(
        Rect.fromLTRB(
          x - bodyWidth / 2,
          top,
          x + bodyWidth / 2,
          math.max(top + 1.5, bottom),
        ),
        Paint()..color = color,
      );
    }

    void drawLevel(double value, Color color) {
      if (value <= 0 || value < minPrice || value > maxPrice) return;
      final levelY = y(value);
      final paint = Paint()
        ..color = color.withOpacity(.9)
        ..strokeWidth = 1
        ..style = PaintingStyle.stroke;
      for (double x = 0; x < size.width; x += 9) {
        canvas.drawLine(
          Offset(x, levelY),
          Offset(math.min(x + 5, size.width), levelY),
          paint,
        );
      }
    }

    drawLevel(entry, blue);
    drawLevel(stop, red);
    drawLevel(target, green);
  }

  @override
  bool shouldRepaint(covariant LiveCandlePainter old) =>
      old.candles != candles ||
      old.entry != entry ||
      old.stop != stop ||
      old.target != target;
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
