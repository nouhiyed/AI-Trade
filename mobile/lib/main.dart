import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'screens/performance_screen.dart';
import 'screens/pro_chart_screen.dart';
import 'screens/closed_trade_detail_screen.dart';
import 'services/api_service.dart';
import 'widgets/coin_logo.dart';

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


class AppAtmospherePainter extends CustomPainter {
  final bool dark;
  const AppAtmospherePainter({required this.dark});

  @override
  void paint(Canvas canvas, Size size) {
    final base = dark ? const Color(0xFF040916) : const Color(0xFFF1F6FC);
    canvas.drawRect(Offset.zero & size, Paint()..color = base);

    final glowA = Offset(size.width * .18, size.height * .30);
    final glowB = Offset(size.width * .88, size.height * .64);
    for (final entry in [
      [glowA, size.width * .78, const Color(0xFF087BFF)],
      [glowB, size.width * .72, const Color(0xFF00D9C2)],
      [Offset(size.width * .56, size.height * .96), size.width * .55, const Color(0xFF754BFF)],
    ]) {
      final center = entry[0] as Offset;
      final radius = entry[1] as double;
      final color = entry[2] as Color;
      canvas.drawCircle(
        center,
        radius,
        Paint()
          ..shader = RadialGradient(
            colors: [
              color.withOpacity(dark ? .17 : .075),
              color.withOpacity(dark ? .055 : .025),
              Colors.transparent,
            ],
            stops: const [0, .48, 1],
          ).createShader(Rect.fromCircle(center: center, radius: radius)),
      );
    }

    // Faint technical grid.
    final grid = Paint()
      ..color = (dark ? const Color(0xFF62CFFF) : const Color(0xFF527C9A))
          .withOpacity(dark ? .055 : .045)
      ..strokeWidth = .65;
    for (double x = 0; x < size.width; x += 38) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    for (double y = 0; y < size.height; y += 38) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }

    // Holographic candlestick market stream on the right side.
    final double candleWidth = size.width * .009 < 3.0 ? 3.0 : size.width * .009;
    final double gap = candleWidth * 1.8;
    final double chartLeft = size.width * .48;
    final double chartTop = size.height * .10;
    final double chartHeight = size.height * .72;
    final up = Paint()..color = const Color(0xFF00E5B0).withOpacity(dark ? .30 : .13);
    final down = Paint()..color = const Color(0xFFFF557D).withOpacity(dark ? .27 : .12);
    final wickUp = Paint()..color = const Color(0xFF00E5B0).withOpacity(dark ? .42 : .20)..strokeWidth = 1;
    final wickDown = Paint()..color = const Color(0xFFFF557D).withOpacity(dark ? .38 : .18)..strokeWidth = 1;
    for (int i = 0; i < 34; i++) {
      final double x = chartLeft + i.toDouble() * gap;
      if (x > size.width + candleWidth) break;
      final double wave = math.sin(i * .57) * .20 + math.cos(i * .21) * .14;
      final double centerY = chartTop + chartHeight * (.48 - wave - i.toDouble() * .004);
      final double bodyHeight = 8.0 + (math.sin(i * 1.73).abs() * size.height * .035);
      final rising = math.sin(i * 1.31) > -.12;
      final double top = centerY - bodyHeight * .5;
      final double bottom = centerY + bodyHeight * .5;
      canvas.drawLine(
        Offset(x + candleWidth * .5, top - 7),
        Offset(x + candleWidth * .5, bottom + 8),
        rising ? wickUp : wickDown,
      );
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(x, top, candleWidth, bodyHeight),
          const Radius.circular(1.5),
        ),
        rising ? up : down,
      );
    }

    // AI neural network: connected nodes and illuminated signal paths.
    final nodes = <Offset>[
      Offset(size.width * .08, size.height * .18),
      Offset(size.width * .27, size.height * .13),
      Offset(size.width * .37, size.height * .31),
      Offset(size.width * .16, size.height * .39),
      Offset(size.width * .31, size.height * .57),
      Offset(size.width * .08, size.height * .70),
      Offset(size.width * .43, size.height * .78),
      Offset(size.width * .68, size.height * .90),
      Offset(size.width * .91, size.height * .22),
    ];
    final links = Paint()
      ..color = const Color(0xFF25BFFF).withOpacity(dark ? .16 : .08)
      ..strokeWidth = 1.1;
    const pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (4, 6), (6, 7), (2, 8), (1, 4)];
    for (final pair in pairs) {
      canvas.drawLine(nodes[pair.$1], nodes[pair.$2], links);
    }
    for (int i = 0; i < nodes.length; i++) {
      final color = i.isEven ? const Color(0xFF00E5C3) : const Color(0xFF7D83FF);
      canvas.drawCircle(
        nodes[i],
        7,
        Paint()..color = color.withOpacity(dark ? .055 : .025),
      );
      canvas.drawCircle(
        nodes[i],
        2.2,
        Paint()..color = color.withOpacity(dark ? .40 : .18),
      );
    }

    // Abstract AI core silhouette: luminous orbital rings, deliberately subtle
    // so it never competes with the live trading controls or chart labels.
    final core = Offset(size.width * .20, size.height * .48);
    final orbit = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..color = const Color(0xFF00D9E8).withOpacity(dark ? .12 : .055);
    canvas.save();
    canvas.translate(core.dx, core.dy);
    canvas.rotate(-.48);
    canvas.drawOval(
      Rect.fromCenter(center: Offset.zero, width: size.width * .62, height: size.width * .20),
      orbit,
    );
    canvas.rotate(1.0);
    orbit.color = const Color(0xFF8B70FF).withOpacity(dark ? .11 : .05);
    canvas.drawOval(
      Rect.fromCenter(center: Offset.zero, width: size.width * .50, height: size.width * .17),
      orbit,
    );
    canvas.restore();
    canvas.drawCircle(
      core,
      size.width * .12,
      Paint()
        ..shader = RadialGradient(
          colors: [
            const Color(0xFF00D9E8).withOpacity(dark ? .09 : .035),
            Colors.transparent,
          ],
        ).createShader(Rect.fromCircle(center: core, radius: size.width * .12)),
    );

    // Small illuminated data rails.
    final rail = Paint()
      ..color = const Color(0xFF168DFF).withOpacity(dark ? .17 : .07)
      ..strokeWidth = 1;
    canvas.drawLine(
      Offset(size.width * .04, size.height * .84),
      Offset(size.width * .44, size.height * .84),
      rail,
    );
    canvas.drawLine(
      Offset(size.width * .60, size.height * .12),
      Offset(size.width * .96, size.height * .12),
      rail,
    );
  }

  @override
  bool shouldRepaint(covariant AppAtmospherePainter old) => old.dark != dark;
}

class _BalanceAiPainter extends CustomPainter {
  final bool dark;
  final bool english;
  const _BalanceAiPainter({required this.dark, required this.english});

  @override
  void paint(Canvas canvas, Size size) {
    // Stronger AI + trading artwork, deliberately kept on the left side
    // so the account figures remain clear on the right.
    final area = Rect.fromLTWH(0, 0, size.width * .49, size.height);
    final center = Offset(size.width * .235, size.height * .51);
    final radius = size.height * .235;
    const cyan = Color(0xFF18E0C5);
    const blue = Color(0xFF268BFF);
    const violet = Color(0xFF9B68FF);

    final glow = Paint()
      ..shader = RadialGradient(
        colors: [
          cyan.withOpacity(dark ? .30 : .16),
          blue.withOpacity(dark ? .19 : .10),
          violet.withOpacity(dark ? .10 : .05),
          Colors.transparent,
        ],
        stops: const [0, .34, .68, 1],
      ).createShader(Rect.fromCircle(center: center, radius: radius * 2.35));
    canvas.drawCircle(center, radius * 2.35, glow);

    // Subtle market grid behind the neural core.
    final grid = Paint()
      ..color = cyan.withOpacity(dark ? .09 : .055)
      ..strokeWidth = .7;
    for (double x = 8; x < size.width * .48; x += 25) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    for (double y = 12; y < size.height; y += 25) {
      canvas.drawLine(Offset(0, y), Offset(size.width * .48, y), grid);
    }

    // Binance-like market candles rising behind the AI core.
    final candleData = <(double, double, double, bool)>[
      (.035, .72, .54, true), (.085, .61, .39, false),
      (.135, .66, .43, true), (.185, .51, .30, true),
      (.235, .57, .35, false), (.285, .43, .23, true),
      (.335, .49, .27, true), (.385, .34, .17, false),
      (.435, .40, .20, true),
    ];
    for (final candle in candleData) {
      final x = size.width * candle.$1;
      final top = size.height * candle.$3;
      final bottom = size.height * candle.$2;
      final color = candle.$4 ? cyan : const Color(0xFFFF6487);
      final paint = Paint()
        ..color = color.withOpacity(dark ? .72 : .46)
        ..strokeWidth = 1.2;
      canvas.drawLine(Offset(x, top - size.height * .055),
          Offset(x, bottom + size.height * .055), paint);
      final bodyTop = top < bottom ? top : bottom;
      final bodyBottom = top < bottom ? bottom : top;
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTRB(x - 2.3, bodyTop, x + 2.3,
              bodyBottom < bodyTop + 5 ? bodyTop + 5 : bodyBottom),
          const Radius.circular(2),
        ),
        Paint()..color = color.withOpacity(dark ? .82 : .58),
      );
    }

    // Layered orbital rings around the AI nucleus.
    final orbit = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.35
      ..color = blue.withOpacity(dark ? .52 : .30);
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(-.48);
    canvas.drawOval(
      Rect.fromCenter(center: Offset.zero,
          width: radius * 3.0, height: radius * .92),
      orbit,
    );
    canvas.rotate(1.02);
    orbit.color = cyan.withOpacity(dark ? .66 : .38);
    canvas.drawOval(
      Rect.fromCenter(center: Offset.zero,
          width: radius * 2.65, height: radius * .80),
      orbit,
    );
    canvas.rotate(.72);
    orbit.color = violet.withOpacity(dark ? .50 : .28);
    canvas.drawOval(
      Rect.fromCenter(center: Offset.zero,
          width: radius * 2.2, height: radius * .72),
      orbit,
    );
    canvas.restore();

    // Glowing central processor.
    final coreGlow = Paint()
      ..shader = RadialGradient(
        colors: [
          cyan.withOpacity(dark ? .58 : .36),
          blue.withOpacity(dark ? .34 : .20),
          Colors.transparent,
        ],
      ).createShader(Rect.fromCircle(center: center, radius: radius * .95));
    canvas.drawCircle(center, radius * .95, coreGlow);
    canvas.drawCircle(center, radius * .48,
        Paint()..color = const Color(0xFF071A2B).withOpacity(dark ? .72 : .48));
    canvas.drawCircle(center, radius * .48,
        Paint()..style = PaintingStyle.stroke..strokeWidth = 1.5
          ..color = cyan.withOpacity(dark ? .85 : .60));

    // Neural connections and active nodes.
    final nodes = <Offset>[
      Offset(size.width * .055, size.height * .27),
      Offset(size.width * .12, size.height * .12),
      Offset(size.width * .25, size.height * .10),
      Offset(size.width * .405, size.height * .25),
      Offset(size.width * .43, size.height * .68),
      Offset(size.width * .28, size.height * .88),
      Offset(size.width * .085, size.height * .76),
    ];
    const edges = <(int, int)>[
      (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 0),
      (0, 3), (1, 5), (2, 4),
    ];
    final link = Paint()
      ..color = blue.withOpacity(dark ? .34 : .20)
      ..strokeWidth = 1.0;
    for (final edge in edges) {
      canvas.drawLine(nodes[edge.$1], nodes[edge.$2], link);
    }
    for (var i = 0; i < nodes.length; i++) {
      final color = i.isEven ? cyan : violet;
      canvas.drawCircle(nodes[i], i.isEven ? 3.1 : 2.5,
          Paint()..color = color.withOpacity(dark ? .92 : .68));
      canvas.drawCircle(nodes[i], i.isEven ? 7.5 : 6.2,
          Paint()..style = PaintingStyle.stroke..strokeWidth = 1.0
            ..color = color.withOpacity(dark ? .42 : .25));
    }

    // A luminous price trace links the chart to the AI nucleus.
    final trace = Path()
      ..moveTo(size.width * .025, size.height * .63)
      ..cubicTo(size.width * .12, size.height * .56,
          size.width * .13, size.height * .48,
          size.width * .21, size.height * .52)
      ..cubicTo(size.width * .30, size.height * .57,
          size.width * .33, size.height * .34,
          size.width * .46, size.height * .29);
    canvas.drawPath(trace, Paint()
      ..color = cyan.withOpacity(dark ? .68 : .42)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round);
  }

  @override
  bool shouldRepaint(covariant _BalanceAiPainter oldDelegate) =>
      oldDelegate.dark != dark || oldDelegate.english != english;
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
  String _apiVersion = '';
  Map<String, dynamic> demoData = {};
  Map<String, dynamic> agentControls = {};
  final Set<String> closingPositionIds = {};
  final TextEditingController _telegramTokenController = TextEditingController();
  final TextEditingController _telegramChatController = TextEditingController();
  Map<String, dynamic> _telegramStatus = {};
  bool _telegramBusy = false;
  Timer? _refreshTimer;
  Timer? _statusTimer;
  final Map<String, List<Map<String, double>>> _marketCandles = {};
  final Map<String, List<String>> _marketSymbols = {};
  final Map<String, Map<String, String>> _marketSymbolNames = {};
  final Map<String, String> _marketSymbolErrors = {};
  final Map<String, String> _selectedSymbols = {
    'futures': 'BTCUSDT',
    'spot': 'BTCUSDT',
  };
  final Map<String, String> _selectedIntervals = {
    'futures': '5m',
    'spot': '5m',
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
      await _loadTelegramStatus();
      if (!mounted) return;
      await _refreshMarketData(loadSymbols: true);
    }();
    // Poll position state separately so automatic closes leave the live portfolio promptly.
    _statusTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      if (!mounted) return;
      await _refreshStatus();
    });
    _refreshTimer = Timer.periodic(const Duration(seconds: 15), (_) async {
      if (!mounted) return;
      await _refreshMarketData();
    });
  }

  Future<void> _refreshStatus() async {
    if (apiBusy) return;
    setState(() => apiBusy = true);
    try {
      Object? lastError;
      Map<String, dynamic>? data;
      // Brief retries smooth over the momentary gap while Termux is starting
      // or Android is reconnecting the local loopback service.
      for (var attempt = 0; attempt < 3; attempt++) {
        try {
          data = await ApiService.status();
          break;
        } catch (error) {
          lastError = error;
          if (attempt < 2) {
            await Future.delayed(Duration(milliseconds: 700 * (attempt + 1)));
          }
        }
      }
      if (!mounted) return;
      if (data == null) {
        setState(() {
          apiOnline = false;
          _apiVersion = lastError == null ? '' : 'CONNECTION_ERROR';
        });
        return;
      }
      _applyStatus(data);
      final version = '${data['api_version'] ?? ''}';
      setState(() {
        _apiVersion = version;
        apiOnline = version == '2026.11.12.1';
      });
    } finally {
      if (mounted) setState(() => apiBusy = false);
    }
  }

  List<Map<String, double>> _normalizeCandles(dynamic raw) {
    if (raw is! List) return [];
    final result = <Map<String, double>>[];
    double n(dynamic v) => double.tryParse('$v') ?? 0;
    double seconds(dynamic v) {
      final value = n(v);
      if (value >= 1000000000000) return value / 1000;
      return value;
    }
    for (final item in raw) {
      try {
        late final Map<String, double> candle;
        if (item is Map) {
          candle = {
            'time': seconds(item['time'] ?? item['open_time'] ?? item['timestamp'] ?? item['t']),
            'open': n(item['open'] ?? item['o']),
            'high': n(item['high'] ?? item['h']),
            'low': n(item['low'] ?? item['l']),
            'close': n(item['close'] ?? item['c']),
            'volume': n(item['volume'] ?? item['v']),
          };
        } else if (item is List && item.length >= 5) {
          candle = {
            'time': seconds(item[0]),
            'open': n(item[1]),
            'high': n(item[2]),
            'low': n(item[3]),
            'close': n(item[4]),
            'volume': item.length > 5 ? n(item[5]) : 0,
          };
        } else {
          continue;
        }
        if (candle['time']! > 0 && candle['high']! > 0 && candle['low']! > 0) {
          result.add(candle);
        }
      } catch (_) {}
    }
    result.sort((a, b) => a['time']!.compareTo(b['time']!));
    return result;
  }

  Future<void> _loadMarketSymbols(String market) async {
    try {
      final result = await ApiService.marketSymbols(market);
      if (!mounted) return;
      setState(() => _marketSymbolErrors.remove(market));
      dynamic raw = result['symbols'] ?? result['data'] ?? result['items'];
      if (raw is Map) {
        raw = raw['symbols'] ?? raw['items'] ?? raw['data'];
      }
      final symbols = <String>[];
      final names = <String, String>{};
      if (raw is List) {
        for (final item in raw) {
          final value = item is Map
              ? (item['symbol'] ?? item['s'] ?? item['pair'])
              : item;
          if (value != null && '$value'.isNotEmpty) {
            final symbol = '$value';
            symbols.add(symbol);
            if (item is Map) {
              final name = '${item['name'] ?? item['display'] ?? item['ticker'] ?? ''}'.trim();
              if (name.isNotEmpty && name != symbol) names[symbol] = name;
            }
          }
        }
      }
      if (symbols.isNotEmpty) {
        setState(() {
          _marketSymbols[market] = symbols.toSet().toList()..sort();
          _marketSymbolNames[market] = names;
          if (!_marketSymbols[market]!.contains(_selectedSymbols[market])) {
            _selectedSymbols[market] = _marketSymbols[market]!.first;
          }
        });
      } else {
        if (mounted) setState(() {
          _marketSymbolErrors[market] = tr('لم تُرجع Binance أي أزواج لهذا السوق.', 'Binance returned no symbols for this market.');
        });
      }
    } catch (error) {
      if (mounted) setState(() => _marketSymbolErrors[market] = '$error');
    }
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

  Future<void> _loadPositionCandles(
    String market, String symbol, {String interval = '5m'}
  ) async {
    if (symbol.isEmpty) return;
    final key = '$market:$symbol:$interval';
    if (_marketLoading.contains(key)) return;
    _marketLoading.add(key);
    try {
      final result = await ApiService.marketCandles(
        market: market,
        symbol: symbol,
        interval: interval,
        limit: 180,
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
      for (final market in ['futures', 'spot']) {
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
          final market = domain.contains('future') ? 'futures' : 'spot';
          final symbol = '${position['symbol'] ?? ''}';
          final interval = '${position['entry_timeframe'] ?? position['timeframe'] ?? '5m'}';
          final key = '$market:$symbol:$interval';
          if (symbol.isNotEmpty && refreshed.add(key)) {
            await _loadPositionCandles(market, symbol, interval: interval);
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
                leading: CoinLogo(symbol: symbol, size: 30),
                title: Text(
                  _marketSymbolNames[market]?[symbol] ?? symbol,
                  style: TextStyle(color: widget.text, fontWeight: FontWeight.w700),
                ),
                subtitle: Text(symbol, style: TextStyle(color: widget.muted, fontSize: 10)),
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
    final raw = demoData['open_positions'];
    final openPositions = raw is List
        ? raw.whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item)).toList()
        : <Map<String, dynamic>>[];
    final closedRaw = demoData['closed_positions'];
    final closedPositions = closedRaw is List
        ? closedRaw.whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item)).toList()
        : <Map<String, dynamic>>[];
    final positions = <Map<String, dynamic>>[
      ...openPositions,
      ...closedPositions,
    ].where((p) => '${p['domain'] ?? market}'.toLowerCase() == market)
      .toList();

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
              child: Text(title, style: TextStyle(
                color: widget.text,
                fontWeight: FontWeight.w900,
                fontSize: 15,
              )),
            ),
            Text(market.toUpperCase(), style: TextStyle(
              color: accent, fontSize: 9, fontWeight: FontWeight.bold,
            )),
          ]),
          const SizedBox(height: 7),
          Row(children: [
            CoinLogo(
              symbol: _selectedSymbols[market]?.isNotEmpty == true
                  ? _selectedSymbols[market]!
                  : 'BTCUSDT',
              size: 28,
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Text(
                _marketSymbolNames[market]?[_selectedSymbols[market] ?? ''] ??
                    (_selectedSymbols[market]?.isNotEmpty == true
                        ? _selectedSymbols[market]!
                        : tr('تحميل قائمة العملات...', 'Loading market symbols...')),
                style: TextStyle(
                  color: accent,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            TextButton.icon(
              onPressed: () => _chooseMarketSymbol(market),
              icon: const Icon(Icons.currency_exchange, size: 16),
              label: Text(tr('العملات', 'Coins')),
            ),
          ]),
          const SizedBox(height: 10),
          ProChartScreen(
            key: ValueKey('market-pro-chart-$market-${_selectedSymbols[market] ?? ''}'),
            embedded: true,
            initialMarket: market,
            initialSymbol: ((_selectedSymbols[market]?.isNotEmpty ?? false)
                ? _selectedSymbols[market]!
                : 'BTCUSDT'),
            english: en,
            bg: widget.bg,
            panel: widget.panel,
            text: widget.text,
            muted: widget.muted,
            positions: positions,
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
          'تم إغلاق الصفقة وحفظها في الأرشيف.',
          'Trade closed and saved to the archive.',
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
    final rawOpen = demoData['open_positions'] ??
        demoData['positions'] ??
        demoData['items'];
    final openPositions = rawOpen is List
        ? rawOpen.whereType<Map>().map((item) {
            final position = Map<String, dynamic>.from(item);
            position['id'] = position['id'] ??
                position['position_id'] ??
                position['trade_id'] ??
                '';
            return position;
          }).where((item) =>
              item['id'].toString().isNotEmpty &&
              !{'DEMO_CLOSED', 'CLOSED'}.contains(
                '${item['status'] ?? ''}'.toUpperCase(),
              )).toList()
        : <Map<String, dynamic>>[];
    final rawClosed = demoData['closed_positions'];
    final closedPositions = rawClosed is List
        ? rawClosed.whereType<Map>().map((item) {
            final trade = Map<String, dynamic>.from(item);
            trade['id'] = trade['id'] ??
                trade['position_id'] ??
                trade['trade_id'] ??
                '';
            return trade;
          }).where((item) => item['id'].toString().isNotEmpty).toList()
        : <Map<String, dynamic>>[];
    demoData['open_positions'] = openPositions;
    demoData['closed_positions'] = closedPositions;
    agentControls = controls is Map
        ? Map<String, dynamic>.from(controls)
        : <String, dynamic>{};
  }

  bool get allAgentsEnabled {
    const domains = ['futures', 'spot'];
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

  Future<void> _loadTelegramStatus() async {
    if (!apiOnline) return;
    try {
      final status = await ApiService.telegramStatus();
      if (mounted) setState(() => _telegramStatus = status);
    } catch (_) {}
  }

  Future<void> _configureTelegram() async {
    final token = _telegramTokenController.text.trim();
    final chatId = _telegramChatController.text.trim();
    if (token.isEmpty || chatId.isEmpty) {
      notify(tr('أدخل Bot Token و Chat ID أولاً', 'Enter both Bot Token and Chat ID'));
      return;
    }
    if (!apiOnline || _telegramBusy) return;
    setState(() => _telegramBusy = true);
    try {
      final result = await ApiService.configureTelegram(
        botToken: token,
        chatId: chatId,
      );
      if (!mounted) return;
      setState(() {
        _telegramStatus = result;
        _telegramTokenController.clear();
      });
      notify(tr('تم حفظ إعدادات Telegram. أرسل رسالة اختبار للتأكد.', 'Telegram settings saved. Send a test message to verify delivery.'));
    } catch (error) {
      if (mounted) {
        final detail = error.toString();
        if (detail.contains('Not found') || detail.contains('404')) {
          notify(tr(
            'خادم Termux قديم ولا يحتوي مسار Telegram. حدّث ملفات AI-Trader وأعد تشغيل الخادم.',
            'Your Termux API is outdated and lacks the Telegram route. Update AI-Trader files and restart the server.',
          ));
        } else {
          notify('${tr('فشل حفظ Telegram: ', 'Telegram setup failed: ')}$error');
        }
      }
    } finally {
      if (mounted) setState(() => _telegramBusy = false);
    }
  }

  Future<void> _testTelegram() async {
    if (!apiOnline || _telegramBusy) return;
    setState(() => _telegramBusy = true);
    try {
      final result = await ApiService.testTelegram();
      if (!mounted) return;
      setState(() => _telegramStatus = Map<String, dynamic>.from(result['status'] ?? {}));
      notify(result['sent'] == true
          ? tr('وصلت رسالة الاختبار إلى Telegram بنجاح', 'Telegram test message delivered')
          : '${tr('فشل إرسال Telegram: ', 'Telegram delivery failed: ')}${result['reason'] ?? 'Unknown error'}');
    } catch (error) {
      if (mounted) notify('${tr('فشل إرسال Telegram: ', 'Telegram delivery failed: ')}$error');
    } finally {
      if (mounted) setState(() => _telegramBusy = false);
    }
  }

  Widget _telegramSettingsCard() {
    final configured = _telegramStatus['configured'] == true;
    return _panel(
      border: (configured ? green : blue).withOpacity(.3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.send_rounded, color: Color(0xFF29A9EB), size: 25),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  tr('إشعارات Telegram', 'Telegram notifications'),
                  style: TextStyle(color: widget.text, fontWeight: FontWeight.w800),
                ),
              ),
              Icon(
                configured ? Icons.check_circle : Icons.error_outline,
                color: configured ? green : widget.muted,
                size: 19,
              ),
            ],
          ),
          const SizedBox(height: 7),
          Text(
            !apiOnline
                ? tr(
                    'خادم Termux قديم أو غير محدث. حدّث ملفات المشروع وأعد تشغيل API.',
                    'Termux API is outdated. Pull the latest project files and restart the API.',
                  )
                : configured
                    ? tr('البوت مربوط — تحقق من وصول الرسائل', 'Bot configured — verify message delivery')
                    : tr('أدخل بيانات البوت لربط الإشعارات', 'Enter bot credentials to enable alerts'),
            style: TextStyle(color: widget.muted, fontSize: 10),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _telegramTokenController,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            style: TextStyle(color: widget.text, fontSize: 12),
            decoration: InputDecoration(
              labelText: 'Telegram Bot Token',
              labelStyle: TextStyle(color: widget.muted, fontSize: 11),
              filled: true,
              fillColor: widget.bg.withOpacity(.55),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              prefixIcon: const Icon(Icons.key, color: cyan, size: 18),
            ),
          ),
          const SizedBox(height: 9),
          TextField(
            controller: _telegramChatController,
            keyboardType: TextInputType.text,
            autocorrect: false,
            style: TextStyle(color: widget.text, fontSize: 12),
            decoration: InputDecoration(
              labelText: 'Telegram Chat ID',
              labelStyle: TextStyle(color: widget.muted, fontSize: 11),
              filled: true,
              fillColor: widget.bg.withOpacity(.55),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              prefixIcon: const Icon(Icons.forum_outlined, color: cyan, size: 18),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: !apiOnline || _telegramBusy ? null : _configureTelegram,
                  icon: const Icon(Icons.save_outlined, size: 17),
                  label: Text(tr('حفظ الربط', 'Save')),
                ),
              ),
              const SizedBox(width: 9),
              Expanded(
                child: FilledButton.icon(
                  onPressed: !apiOnline || _telegramBusy || !configured ? null : _testTelegram,
                  icon: const Icon(Icons.send_rounded, size: 16),
                  label: Text(tr('اختبار الإرسال', 'Test send')),
                  style: FilledButton.styleFrom(backgroundColor: const Color(0xFF168BC4)),
                ),
              ),
            ],
          ),
          if (_telegramStatus['last_error'] != null) ...[
            const SizedBox(height: 7),
            Text(
              '${tr('آخر خطأ: ', 'Last error: ')}${_telegramStatus['last_error']}',
              style: const TextStyle(color: red, fontSize: 10),
            ),
          ],
        ],
      ),
    );
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _statusTimer?.cancel();
    _telegramTokenController.dispose();
    _telegramChatController.dispose();
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
      backgroundColor: Colors.transparent,
      body: Stack(
        fit: StackFit.expand,
        children: [
          CustomPaint(painter: AppAtmospherePainter(dark: widget.dark)),
          SafeArea(
        bottom: false,
        child: Column(
          children: [
            _topBar(),
            Expanded(
              // Keep pages mounted so navigation never resets autopilot controls.
              child: IndexedStack(index: page, children: pages),
            ),
            _bottomBar(titles),
          ],
        ),
          ),
        ],
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
          _heading(
            tr('فريق الوكلاء', 'AGENT NETWORK'),
            '2 AGENTS',
            Icons.hub,
          ),
          const SizedBox(height: 10),
          _agentRow('futures', 'FUTURES AGENT', tr('العقود الآجلة', 'Futures'), cyan),
          _agentRow('spot', 'SPOT AGENT', tr('السوق الفوري', 'Spot'), blue),
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
                      tr('نظام متعدد الوكلاء', 'MULTI-AGENT SYSTEM'),
                      style: TextStyle(
                        color: widget.text,
                        fontSize: 20,
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
    final realized = money(['net_realized_pnl']);
    final fees = money(['total_fees', 'fees']);
    final openCount = demoData['open_count'] ??
        (demoData['open_positions'] is List
            ? (demoData['open_positions'] as List).length
            : 0);
    final totalTrades = demoData['total_trades'] ?? 0;

    return _panel(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Stack(
          children: [
            Positioned.fill(
              child: IgnorePointer(child: CustomPaint(painter: _BalanceAiPainter(dark: widget.dark, english: en))),
            ),
            Column(
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
              _metric(tr('صافي بعد الرسوم', 'NET AFTER FEES'), apiOnline ? realized : '—', widget.text),
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
          ],
        ),
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

  Widget _proTools() => Align(
        alignment: AlignmentDirectional.centerStart,
        child: OutlinedButton.icon(
          onPressed: _openPerformance,
          icon: const Icon(Icons.insights, size: 18),
          label: Text(tr('الأداء والآلي', 'Autopilot')),
        ),
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
    ],
  );

  Widget _positionLiveChart(Map<String, dynamic> position) {
    final domain = '${position['domain'] ?? 'spot'}'.toLowerCase();
    final market = domain.contains('future') ? 'futures' : 'spot';
    final symbol = '${position['symbol'] ?? ''}';
    final interval = '${position['entry_timeframe'] ?? position['timeframe'] ?? '5m'}';
    final key = '$market:$symbol:$interval';
    final candles = _marketCandles[key] ?? [];
    final current = candles.isNotEmpty ? candles.last['close']! : 0.0;
    final entry = double.tryParse('${position['entry_price'] ?? ''}') ?? 0;
    final stop = double.tryParse('${position['stop_loss'] ?? ''}') ?? 0;
    final target = double.tryParse('${position['take_profit'] ?? ''}') ?? 0;
    final target2 = double.tryParse('${position['take_profit_2'] ?? ''}') ?? 0;
    final timeframeSeconds = <String, int>{
      '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400,
    }[interval] ?? 300;
    final storedEntryTime = int.tryParse('${position['entry_candle_time'] ?? ''}') ?? 0;
    final openedAtMs = int.tryParse('${position['opened_at_ms'] ?? ''}') ?? 0;
    final entryCandleTime = storedEntryTime > 0
        ? (storedEntryTime > 1000000000000 ? storedEntryTime ~/ 1000 : storedEntryTime)
        : openedAtMs > 0
            ? ((openedAtMs ~/ 1000) ~/ timeframeSeconds) * timeframeSeconds
            : 0;

    if (symbol.isNotEmpty && candles.isEmpty && !_marketLoading.contains(key)) {
      Future.microtask(() => _loadPositionCandles(market, symbol, interval: interval));
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
                      target2: target2,
                      entryCandleTime: entryCandleTime,
                      direction: direction,
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
            final target2 = position['take_profit_2']?.toString();
            final runnerPct = (100 - (double.tryParse('${position['tp1_close_pct']}') ?? 70))
                .toStringAsFixed(0);
            final confirmation = '${position['entry_confirmation'] ?? ''}'.trim();
            final structureSupport = position['structure_support']?.toString();
            final structureResistance = position['structure_resistance']?.toString();
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
                        if (domain == 'FUTURES')
                          Expanded(child: _metric('LEVERAGE', '${position['leverage'] ?? 1}x', widget.text)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    _positionLiveChart(position),
                    if (confirmation.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        '${tr('تأكيد الدخول', 'ENTRY CONFIRMATION')}: $confirmation',
                        style: TextStyle(color: widget.muted, fontSize: 10, height: 1.35),
                      ),
                    ],
                    if ((structureSupport != null && structureSupport.isNotEmpty) ||
                        (structureResistance != null && structureResistance.isNotEmpty)) ...[
                      const SizedBox(height: 8),
                      Row(children: [
                        if (structureSupport != null && structureSupport.isNotEmpty)
                          Expanded(child: _metric(tr('الدعم الهيكلي', 'STRUCTURAL SUPPORT'), structureSupport, green)),
                        if (structureResistance != null && structureResistance.isNotEmpty)
                          Expanded(child: _metric(tr('المقاومة الهيكلية', 'STRUCTURAL RESISTANCE'), structureResistance, red)),
                      ]),
                    ],
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(child: _metric('STOP LOSS', stop, red)),
                        Expanded(child: _metric('TAKE PROFIT 1', target, green)),
                      ],
                    ),
                    if (target2 != null && target2.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Row(children: [
                          Expanded(child: _metric('TAKE PROFIT 2', target2, cyan)),
                          Expanded(child: _metric(
                            tr('إغلاق متبقٍ', 'RUNNER'),
                            '$runnerPct%',
                            widget.muted,
                          )),
                        ]),
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

  Widget _closedPositionsSection() {
    final raw = demoData['closed_positions'];
    final trades = raw is List
        ? raw.whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item)).toList()
        : <Map<String, dynamic>>[];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _heading(
          tr('أرشيف الصفقات المغلقة', 'CLOSED TRADE ARCHIVE'),
          '${trades.length} CLOSED',
          Icons.archive_outlined,
        ),
        const SizedBox(height: 10),
        if (trades.isEmpty)
          _panel(
            child: Center(
              child: Text(
                tr('لا توجد صفقات مغلقة بعد', 'No closed trades yet'),
                style: TextStyle(color: widget.muted),
              ),
            ),
          )
        else
          SizedBox(
            height: 224,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              reverse: en,
              padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
              itemCount: trades.length,
              separatorBuilder: (_, __) => const SizedBox(width: 10),
              itemBuilder: (context, index) {
                final trade = trades[index];
                final symbol = '${trade['symbol'] ?? '—'}';
                final direction = '${trade['direction'] ?? '—'}'.toUpperCase();
                final domain = '${trade['domain'] ?? '—'}'.toUpperCase();
                final entry = trade['entry_price'] ?? trade['entry'] ?? '—';
                final exit = trade['close_price'] ?? trade['exit_price'] ?? '—';
                final timeframe = trade['timeframe'] ??
                    (trade['context'] is Map
                        ? (trade['context'] as Map)['chart_timeframe'] ??
                            (trade['context'] as Map)['timeframe']
                        : null) ?? '5m';
                final pnlValue = double.tryParse(
                  '${trade['net_pnl'] ?? trade['realized_pnl'] ?? 0}',
                ) ?? 0;
                final reason = '${trade['close_reason'] ?? 'CLOSED'}'.toUpperCase();
                final outcomeLabel = pnlValue > 0
                    ? tr('رابحة', 'WIN')
                    : pnlValue < 0 ? tr('خاسرة', 'LOSS') : tr('تعادل', 'BREAKEVEN');
                final closedAt = trade['closed_at'] ?? trade['closed_at_ms'];
                String closedLabel = '—';
                if (closedAt != null) {
                  final stamp = int.tryParse('$closedAt');
                  if (stamp != null && stamp > 0) {
                    final date = DateTime.fromMillisecondsSinceEpoch(
                      stamp < 1000000000000 ? stamp * 1000 : stamp,
                    ).toLocal();
                    closedLabel =
                        '${date.year}-${date.month.toString().padLeft(2, '0')}-'
                        '${date.day.toString().padLeft(2, '0')} '
                        '${date.hour.toString().padLeft(2, '0')}:'
                        '${date.minute.toString().padLeft(2, '0')}';
                  }
                }
                return SizedBox(
                  width: 306,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(18),
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => ClosedTradeDetailScreen(
                            trade: trade,
                            english: en,
                            bg: widget.bg,
                            panel: widget.panel,
                            text: widget.text,
                            muted: widget.muted,
                          ),
                        ),
                      );
                    },
                    child: _panel(
                      border: (pnlValue >= 0 ? green : red).withOpacity(.28),
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
                                    fontSize: 15,
                                  ),
                                ),
                              ),
                              _pill(direction, direction == 'SHORT' ? red : green),
                              const SizedBox(width: 5),
                              _pill(domain, blue),
                              const SizedBox(width: 5),
                              _pill(outcomeLabel, pnlValue >= 0 ? green : red),
                            ],
                          ),
                          const SizedBox(height: 13),
                          _metric(tr('الدخول', 'ENTRY'), '$entry', widget.text),
                          const SizedBox(height: 8),
                          _metric(tr('الخروج', 'EXIT'), '$exit', widget.text),
                          const SizedBox(height: 8),
                          _metric(
                            tr('النتيجة الصافية', 'NET PNL'),
                            '${pnlValue >= 0 ? '+' : ''}${pnlValue.toStringAsFixed(4)} USDT',
                            pnlValue >= 0 ? green : red,
                          ),
                          const Spacer(),
                          Text(
                            '${tr('الإطار', 'TIMEFRAME')}: $timeframe  •  $reason',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(color: widget.muted, fontSize: 9),
                          ),
                          const SizedBox(height: 5),
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  closedLabel,
                                  style: TextStyle(color: widget.muted, fontSize: 10),
                                ),
                              ),
                              const Icon(Icons.open_in_new, color: cyan, size: 15),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
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
          _closedPositionsSection(),
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
          _heading(tr('سجل الصفقات', 'TRADE HISTORY'), 'ARCHIVE', Icons.receipt_long),
          const SizedBox(height: 10),
          _panel(
            child: Text(
              tr(
                'تظهر جميع المراكز المحسومة في أرشيف الصفقات المغلقة أعلاه، ولا تُعرض ضمن المراكز النشطة أو التشارتات الحية.',
                'All settled positions are listed in the closed-trade archive above and are excluded from active positions and live charts.',
              ),
              style: TextStyle(color: widget.muted, fontSize: 11),
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
          _telegramSettingsCard(),
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
            Text(title, style: TextStyle(color: widget.muted, fontSize: 10, fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
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

class HeroMarketAIPainter extends CustomPainter {
  final double t;
  HeroMarketAIPainter(this.t);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width * .48, size.height * .49);
    final coreRadius = size.width * .19;
    final glowRect = Rect.fromCircle(center: center, radius: coreRadius * 2.8);

    // Deep cyan/violet bloom behind the AI processor.
    canvas.drawCircle(
      center,
      coreRadius * 2.8,
      Paint()
        ..shader = RadialGradient(colors: [
          const Color(0xFF00E9D2).withOpacity(.34 + .05 * math.sin(t * math.pi * 2)),
          const Color(0xFF287BFF).withOpacity(.16),
          const Color(0xFF815BFF).withOpacity(.08),
          Colors.transparent,
        ], stops: const [0, .42, .72, 1]).createShader(glowRect),
    );

    // Market candles behind the AI core.
    final candleUp = Paint()..color = const Color(0xFF00E4B5).withOpacity(.72);
    final candleDown = Paint()..color = const Color(0xFFFF5D83).withOpacity(.66);
    final wickUp = Paint()..color = const Color(0xFF00E4B5).withOpacity(.8)..strokeWidth = 1.1;
    final wickDown = Paint()..color = const Color(0xFFFF5D83).withOpacity(.75)..strokeWidth = 1.1;
    for (int i = 0; i < 17; i++) {
      final x = size.width * (.05 + i * .054);
      final wave = math.sin(i * .72) * .22 + math.cos(i * .31) * .10;
      final y = size.height * (.49 - wave - i * .006);
      final h = 8.0 + (i % 4) * 4.0;
      final rising = math.sin(i * 1.4) > -.05;
      canvas.drawLine(Offset(x, y - h), Offset(x, y + h), rising ? wickUp : wickDown);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(center: Offset(x, y), width: 4.2, height: h * 1.05),
          const Radius.circular(1.5),
        ),
        rising ? candleUp : candleDown,
      );
    }

    // Circuit-board links from the shared trading brain to the Futures and Spot domains.
    final nodes = <Offset>[
      Offset(size.width * .12, size.height * .18),
      Offset(size.width * .80, size.height * .16),
      Offset(size.width * .13, size.height * .82),
      Offset(size.width * .83, size.height * .79),
      Offset(size.width * .49, size.height * .04),
      Offset(size.width * .49, size.height * .94),
    ];
    final colors = [
      const Color(0xFF00E5C3),
      const Color(0xFF4C9BFF),
      const Color(0xFF9A78FF),
      const Color(0xFF00D9C2),
      const Color(0xFF4C9BFF),
      const Color(0xFF9A78FF),
    ];
    for (int i = 0; i < nodes.length; i++) {
      final path = Path()
        ..moveTo(center.dx, center.dy)
        ..lineTo((center.dx + nodes[i].dx) * .5, nodes[i].dy)
        ..lineTo(nodes[i].dx, nodes[i].dy);
      canvas.drawPath(
        path,
        Paint()
          ..color = colors[i].withOpacity(.42)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.1,
      );
      canvas.drawCircle(nodes[i], 8, Paint()..color = colors[i].withOpacity(.10));
      canvas.drawCircle(nodes[i], 3.2, Paint()..color = colors[i].withOpacity(.95));
      canvas.drawCircle(
        nodes[i], 6.2,
        Paint()..style = PaintingStyle.stroke..strokeWidth = 1..color = colors[i].withOpacity(.62),
      );
      final progress = (t + i * .17) % 1.0;
      final signal = Offset.lerp(center, nodes[i], progress)!;
      canvas.drawCircle(signal, 2.2, Paint()..color = colors[i].withOpacity(.9));
    }

    // Hexagonal glass processor housing.
    final hex = Path();
    for (int i = 0; i < 6; i++) {
      final a = -math.pi / 2 + i * math.pi / 3;
      final p = Offset(center.dx + math.cos(a) * coreRadius * 1.48,
          center.dy + math.sin(a) * coreRadius * 1.48);
      if (i == 0) {
        hex.moveTo(p.dx, p.dy);
      } else {
        hex.lineTo(p.dx, p.dy);
      }
    }
    hex.close();
    canvas.drawPath(hex, Paint()..color = const Color(0xFF071A2B).withOpacity(.82));
    canvas.drawPath(
      hex,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..shader = const LinearGradient(colors: [
          Color(0xFF00F0D0), Color(0xFF318DFF), Color(0xFF9A72FF), Color(0xFF00F0D0),
        ]).createShader(Rect.fromCircle(center: center, radius: coreRadius * 1.6)),
    );

    // Inner luminous processor die and microchip pins.
    final die = RRect.fromRectAndRadius(
      Rect.fromCenter(center: center, width: coreRadius * 1.45, height: coreRadius * 1.45),
      const Radius.circular(12),
    );
    canvas.drawRRect(
      die,
      Paint()
        ..shader = const RadialGradient(colors: [
          Color(0xFF1C8F9A), Color(0xFF10324D), Color(0xFF0B142B),
        ]).createShader(die.outerRect),
    );
    final pin = Paint()..color = const Color(0xFF7DFCEC).withOpacity(.8)..strokeWidth = 1.6;
    for (int i = -2; i <= 2; i++) {
      final offset = i * coreRadius * .22;
      canvas.drawLine(Offset(center.dx - coreRadius * .93, center.dy + offset),
          Offset(center.dx - coreRadius * .69, center.dy + offset), pin);
      canvas.drawLine(Offset(center.dx + coreRadius * .69, center.dy + offset),
          Offset(center.dx + coreRadius * .93, center.dy + offset), pin);
      canvas.drawLine(Offset(center.dx + offset, center.dy - coreRadius * .93),
          Offset(center.dx + offset, center.dy - coreRadius * .69), pin);
      canvas.drawLine(Offset(center.dx + offset, center.dy + coreRadius * .69),
          Offset(center.dx + offset, center.dy + coreRadius * .93), pin);
    }

    final ai = TextPainter(
      text: const TextSpan(
        text: 'AI',
        style: TextStyle(
          color: Color(0xFFE8FFFE), fontSize: 27, fontWeight: FontWeight.w900,
          letterSpacing: 1.5,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    ai.paint(canvas, Offset(center.dx - ai.width / 2, center.dy - ai.height / 2));

    // Two compact domain markers: Futures and Spot.
    for (int i = 0; i < 2; i++) {
      final x = center.dx + (i == 0 ? -1 : 1) * coreRadius * .34;
      canvas.drawCircle(
        Offset(x, center.dy + coreRadius * 1.95),
        3.5,
        Paint()..color = i == 0 ? const Color(0xFF00E5C3) : const Color(0xFF4C9BFF),
      );
    }
  }

  @override
  bool shouldRepaint(covariant HeroMarketAIPainter old) => old.t != t;
}

class OrbPainter extends CustomPainter {
  final double t;
  OrbPainter(this.t);

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width * .5, size.height * .5);
    final r = size.width * .27;
    final sphere = Rect.fromCircle(center: center, radius: r);

    // Deep ambient glow behind the processor core.
    canvas.drawCircle(
      center,
      r * 2.25,
      Paint()
        ..shader = RadialGradient(
          colors: [
            cyan.withOpacity(.34),
            blue.withOpacity(.14),
            violet.withOpacity(.045),
            Colors.transparent,
          ],
          stops: const [0, .38, .68, 1],
        ).createShader(Rect.fromCircle(center: center, radius: r * 2.25)),
    );

    // Three-dimensional metallic glass sphere with a bright upper-left highlight.
    canvas.drawCircle(
      center,
      r,
      Paint()
        ..shader = const RadialGradient(
          center: Alignment(-.42, -.48),
          radius: .95,
          colors: [
            Color(0xFFE1FFFC),
            Color(0xFF39D8CB),
            Color(0xFF087E91),
            Color(0xFF101A38),
          ],
          stops: [0, .18, .52, 1],
        ).createShader(sphere),
    );
    canvas.drawCircle(
      Offset(center.dx - r * .25, center.dy - r * .34),
      r * .22,
      Paint()
        ..shader = RadialGradient(
          colors: [Colors.white.withOpacity(.72), Colors.white.withOpacity(0)],
        ).createShader(Rect.fromCircle(
          center: Offset(center.dx - r * .25, center.dy - r * .34),
          radius: r * .22,
        )),
    );

    // Curved latitude and longitude traces give the core a dimensional AI-shell.
    final mesh = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = cyan.withOpacity(.28);
    for (int i = -2; i <= 2; i++) {
      final y = center.dy + i * r * .27;
      final half = math.sqrt(math.max(0, r * r - math.pow(i * r * .27, 2)));
      canvas.drawArc(
        Rect.fromCenter(center: Offset(center.dx, y), width: half * 2, height: r * .38),
        math.pi,
        math.pi,
        false,
        mesh,
      );
    }
    for (int i = 0; i < 3; i++) {
      canvas.save();
      canvas.translate(center.dx, center.dy);
      canvas.rotate((t * math.pi * 2) + i * math.pi / 3);
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: r * 3.25, height: r * .78),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = [cyan, blue, violet][i].withOpacity(.88),
      );
      canvas.drawOval(
        Rect.fromCenter(center: Offset.zero, width: r * 2.65, height: r * .54),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = .7
          ..color = Colors.white.withOpacity(.22),
      );
      canvas.restore();
    }

    // Orbiting data nodes and subtle connector beams.
    for (int i = 0; i < 10; i++) {
      final a = t * math.pi * 2 + i * math.pi / 5;
      final point = Offset(
        center.dx + math.cos(a) * r * 1.72,
        center.dy + math.sin(a) * r * .82,
      );
      canvas.drawLine(
        center,
        point,
        Paint()..color = (i.isEven ? cyan : violet).withOpacity(.12),
      );
      canvas.drawCircle(
        point,
        i % 3 == 0 ? 4 : 2.4,
        Paint()..color = i.isEven ? cyan : violet,
      );
      canvas.drawCircle(
        point,
        7,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = .8
          ..color = (i.isEven ? cyan : violet).withOpacity(.38),
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
    final colors = [cyan, blue];
    final nodes = [
      Offset(s.width * .25, s.height * .72),
      Offset(s.width * .75, s.height * .72),
    ];
    for (int i = 0; i < 2; i++) {
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
          text: ['FUTURES', 'SPOT'][i],
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
  final double target2;
  final int entryCandleTime;
  final String direction;

  LiveCandlePainter(
    this.candles, {
    this.entry = 0,
    this.stop = 0,
    this.target = 0,
    this.target2 = 0,
    this.entryCandleTime = 0,
    this.direction = 'LONG',
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty || size.width <= 0 || size.height <= 0) return;

    final visible = candles.length > 160
        ? candles.sublist(candles.length - 160)
        : candles;
    var minPrice = visible.map((c) => c['low']!).reduce(math.min);
    var maxPrice = visible.map((c) => c['high']!).reduce(math.max);
    for (final level in [entry, stop, target, target2]) {
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
    drawLevel(target2, cyan);

    // Mark the exact Binance candle recorded at execution, not a guessed
    // candle based on the chart's current refresh time.
    if (entryCandleTime > 0) {
      final markerIndex = visible.indexWhere((c) =>
          (c['time'] ?? 0).round() == entryCandleTime);
      if (markerIndex >= 0) {
        final candle = visible[markerIndex];
        final x = step * markerIndex + step / 2;
        final isShort = direction.toUpperCase() == 'SHORT';
        final anchorY = y(isShort ? candle['high']! : candle['low']!);
        final markerColor = isShort ? red : green;
        final stemEnd = isShort ? 18.0 : size.height - 18.0;
        final markerPaint = Paint()
          ..color = markerColor
          ..strokeWidth = 2.2;
        canvas.drawLine(Offset(x, anchorY), Offset(x, stemEnd), markerPaint);
        final triangle = Path();
        if (isShort) {
          triangle
            ..moveTo(x, stemEnd + 1)
            ..lineTo(x - 6, stemEnd - 9)
            ..lineTo(x + 6, stemEnd - 9)
            ..close();
        } else {
          triangle
            ..moveTo(x, stemEnd - 1)
            ..lineTo(x - 6, stemEnd + 9)
            ..lineTo(x + 6, stemEnd + 9)
            ..close();
        }
        canvas.drawPath(triangle, Paint()..color = markerColor);
        final label = TextPainter(
          text: TextSpan(
            text: isShort ? 'SHORT ENTRY' : 'LONG ENTRY',
            style: TextStyle(
              color: markerColor,
              fontSize: 9,
              fontWeight: FontWeight.w900,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: size.width * .42);
        final labelX = (x + 7).clamp(2.0, math.max(2.0, size.width - label.width - 2)).toDouble();
        final labelY = isShort ? 2.0 : size.height - label.height - 2;
        label.paint(canvas, Offset(labelX, labelY));
      }
    }
  }

  @override
  bool shouldRepaint(covariant LiveCandlePainter old) =>
      old.candles != candles ||
      old.entry != entry ||
      old.stop != stop ||
      old.target != target ||
      old.target2 != target2 ||
      old.entryCandleTime != entryCandleTime ||
      old.direction != direction;
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
