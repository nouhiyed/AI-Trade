import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../services/api_service.dart';
import '../widgets/coin_logo.dart';

const _up = Color(0xFF26A69A);
const _down = Color(0xFFEF5350);

/// Professional candlestick chart (TradingView Lightweight Charts in a WebView)
/// with indicators and the entry / stop-loss / take-profit lines of open trades.
class ProChartScreen extends StatefulWidget {
  final bool english;
  final Color bg, panel, text, muted;
  final List<Map<String, dynamic>> positions;
  final String initialSymbol;
  final String initialMarket;
  final bool embedded;
  final String initialInterval;
  final bool showSubmitButton;
  final bool lockSelection;

  const ProChartScreen({
    super.key,
    required this.english,
    required this.bg,
    required this.panel,
    required this.text,
    required this.muted,
    required this.positions,
    this.initialSymbol = 'BTCUSDT',
    this.initialMarket = 'futures',
    this.embedded = false,
    this.initialInterval = '5m',
    this.showSubmitButton = true,
    this.lockSelection = false,
  });

  @override
  State<ProChartScreen> createState() => _ProChartScreenState();
}

class _ProChartScreenState extends State<ProChartScreen> {
  late final WebViewController _controller;
  Timer? _timer;
  bool _pageReady = false;
  bool _loading = false;
  bool _submitting = false;
  bool _scalpingBusy = false;
  String? _error;
  String _market = 'futures';
  late String _symbol;
  late String _interval;
  List<String> _symbols = [];
  final Map<String, String> _symbolNames = {};
  double? _lastPrice;

  final Map<String, bool> _indicators = {
    'volume': true,
    'ema': true,
    'bb': false,
    'vwap': false,
    'rsi': false,
    'macd': false,
  };

  List<String> get _availableIntervals {
    if (_market == 'futures') return ['1m', '5m', '15m', '1h'];
    if (_market == 'spot') return ['1m', '5m', '15m', '1h', '4h'];
    return ['1m', '5m', '15m', '1h'];
  }
  static const _markets = ['futures', 'spot'];

  String t(String ar, String en) => widget.english ? en : ar;

  @override
  void initState() {
    super.initState();
    _symbol = widget.initialSymbol;
    _market = widget.initialMarket;
    _interval = widget.initialInterval;
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF0D1117))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (_) {
            _pageReady = true;
            _pushIndicators();
            _loadCandles(fit: true);
          },
        ),
      )
      ..loadHtmlString(_chartHtml);
    _loadSymbols();
    _timer = Timer.periodic(const Duration(seconds: 4), (_) => _loadCandles());
  }

  @override
  void didUpdateWidget(covariant ProChartScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(oldWidget.positions, widget.positions) && _pageReady) {
      _pushLevels();
      _pushTradeMarkers();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _loadSymbols() async {
    try {
      final result = await ApiService.marketSymbols(_market);
      final raw = result['symbols'];
      final list = <String>[];
      final names = <String, String>{};
      if (raw is List) {
        for (final item in raw) {
          if (item is String) {
            list.add(item);
          } else if (item is Map && item['symbol'] != null) {
            final symbol = '${item['symbol']}';
            list.add(symbol);
            final name = '${item['name'] ?? item['display'] ?? item['ticker'] ?? ''}'.trim();
            if (name.isNotEmpty && name != symbol) names[symbol] = name;
          }
        }
      }
      if (mounted && list.isNotEmpty) {
        list.sort();
        setState(() {
          _symbols = list;
          _symbolNames..clear()..addAll(names);
          if (!_symbols.contains(_symbol)) _symbol = _symbols.first;
        });
        if (_pageReady) _loadCandles(fit: true);
      }
    } catch (_) {
      // The chart still works with the current symbol.
    }
  }

  Future<void> _loadCandles({bool fit = false}) async {
    if (!_pageReady || _loading) return;
    _loading = true;
    try {
      final result = await ApiService.marketCandles(
        market: _market,
        symbol: _symbol,
        interval: _interval,
        limit: 300,
        live: true,
      );
      final candles = result['candles'];
      if (candles is List && candles.isNotEmpty) {
        await _controller.runJavaScript(
          'setCandles(${jsonEncode(candles)}, $fit);',
        );
        final last = candles.last;
        if (last is Map && mounted) {
          setState(() {
            _lastPrice = (last['close'] as num?)?.toDouble();
            _error = null;
          });
        }
        _pushLevels();
        _pushTradeMarkers();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '$e';
        });
      }
    } finally {
      _loading = false;
    }
  }

  void _pushLevels() {
    final levels = <Map<String, dynamic>>[];
    for (final p in widget.positions) {
      if ('${p['symbol']}'.toUpperCase() != _symbol.toUpperCase()) continue;
      final status = '${p['status']}';
      if (status != 'DEMO_OPEN' && status != 'DEMO_PARTIALLY_CLOSED') continue;
      void add(String key, String title, String color) {
        final v = double.tryParse('${p[key]}');
        if (v != null && v > 0) {
          levels.add({'price': v, 'title': title, 'color': color});
        }
      }

      add('entry_price', 'ENTRY ${p['direction'] ?? ''}', '#4287f5');
      add('stop_loss', 'SL', '#ef5350');
      add('take_profit', 'TP1', '#26a69a');
      add('take_profit_2', 'TP2', '#00d9c2');
    }
    _controller.runJavaScript('setLevels(${jsonEncode(levels)});');
  }

  void _pushTradeMarkers() {
    if (!_pageReady) return;
    final markers = <Map<String, dynamic>>[];
    final intervalSeconds = <String, int>{
      '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400,
    }[_interval] ?? 300;
    for (final p in widget.positions) {
      if ('${p['symbol']}'.toUpperCase() != _symbol.toUpperCase()) continue;
      final openedAtMs = int.tryParse('${p['opened_at_ms'] ?? p['entry_candle_time_ms'] ?? ''}');
      final storedCandleTime = int.tryParse('${p['entry_candle_time'] ?? ''}');
      final rawSeconds = openedAtMs != null
          ? openedAtMs ~/ 1000
          : storedCandleTime;
      if (rawSeconds == null || rawSeconds <= 0) continue;
      final candleTime = (rawSeconds ~/ intervalSeconds) * intervalSeconds;
      final direction = '${p['direction'] ?? ''}'.toUpperCase();
      final isShort = direction == 'SHORT';
      final origin = '${p['entry_origin'] ?? 'AGENT'}'.toUpperCase();
      final isAuto = origin == 'AUTOPILOT';
      final timeframe = '${p['entry_timeframe'] ?? p['timeframe'] ?? _interval}';
      markers.add({
        'time': candleTime,
        'position': isShort ? 'aboveBar' : 'belowBar',
        'color': isShort ? '#ef5350' : '#26a69a',
        'shape': isShort ? 'arrowDown' : 'arrowUp',
        'text': '${isAuto ? 'AUTO' : 'ENTRY'} ${direction} · ${timeframe}',
      });
    }
    _controller.runJavaScript('setTradeMarkers(${jsonEncode(markers)});');
  }

  Future<void> _chartZoom(double factor) async {
    if (!_pageReady) return;
    try { await _controller.runJavaScript('zoomTimeScale($factor);'); } catch (_) {}
  }

  Future<void> _fitChart() async {
    if (!_pageReady) return;
    try { await _controller.runJavaScript('resetChartView();'); } catch (_) {}
  }

  void _pushIndicators() {
    if (!_pageReady) return;
    _controller.runJavaScript('setIndicators(${jsonEncode(_indicators)});');
  }

  Future<void> _submitToAgent() async {
    if (_submitting || _symbol.isEmpty) return;
    setState(() => _submitting = true);
    try {
      await Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => AgentSubmissionScreen(
            english: widget.english,
            bg: widget.bg,
            panel: widget.panel,
            text: widget.text,
            muted: widget.muted,
            domain: _market,
            symbol: _symbol,
            timeframe: _interval,
            initialPrice: _lastPrice,
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _analyzeScalpingV2() async {
    if (_scalpingBusy || _symbol.isEmpty) return;
    setState(() => _scalpingBusy = true);
    try {
      final result = await ApiService.scalpingSignal(
        market: _market,
        symbol: _symbol,
      );
      if (!mounted) return;
      String price(dynamic value) {
        final number = value is num ? value.toDouble() : double.tryParse('$value');
        return number == null ? '—' : number.toStringAsPrecision(9);
      }
      final success = result['success'] == true;
      final details = success
          ? [
              '${(result['direction'] ?? '').toString()} • ${(result['setup'] ?? '').toString()}',
              'Entry: ${price(result['entry'])}',
              'Stop loss: ${price(result['stop_loss'])}',
              'Take profit: ${price(result['take_profit'])}',
              'Reward/Risk: ${price(result['reward_risk'])}',
              'Net R/R estimate: ${price(result['net_reward_risk'])}',
            ].join('\n')
          : '${result['reason'] ?? t('لا توجد إشارة مطابقة حالياً', 'No qualifying setup right now')}';
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: widget.panel,
          title: Text(
            t('تحليل Scalping v2 • $_symbol', 'Scalping v2 • $_symbol'),
            style: TextStyle(color: widget.text, fontWeight: FontWeight.w800),
          ),
          content: SelectableText(
            '$details\n\n${t('المصدر: Binance لحظي • تحليل فقط، دون إرسال أوامر', 'Source: live Binance • analysis only, no orders submitted')}',
            style: TextStyle(color: widget.text, height: 1.55),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text(t('إغلاق', 'Close')),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$error')),
        );
      }
    } finally {
      if (mounted) setState(() => _scalpingBusy = false);
    }
  }

  Future<void> _pickSymbol() async {
    if (_symbols.isEmpty) await _loadSymbols();
    if (!mounted) return;
    final picked = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: widget.panel,
      isScrollControlled: true,
      builder: (ctx) {
        String filter = '';
        return StatefulBuilder(
          builder: (ctx, setSheet) {
            final shown = _symbols
                .where((s) => s.toUpperCase().contains(filter.toUpperCase()) ||
                    (_symbolNames[s] ?? '').toUpperCase().contains(filter.toUpperCase()))
                .take(80)
                .toList();
            return Padding(
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(ctx).viewInsets.bottom,
              ),
              child: SizedBox(
                height: MediaQuery.of(ctx).size.height * 0.7,
                child: Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: TextField(
                        autofocus: true,
                        style: TextStyle(color: widget.text),
                        decoration: InputDecoration(
                          hintText: t('ابحث عن عملة', 'Search symbol'),
                          prefixIcon: const Icon(Icons.search),
                        ),
                        onChanged: (v) => setSheet(() => filter = v),
                      ),
                    ),
                    Expanded(
                      child: ListView(
                        children: [
                          for (final s in shown)
                            ListTile(
                              leading: CoinLogo(symbol: s, size: 30),
                              title: Text(_symbolNames[s] ?? s,
                                style: TextStyle(color: widget.text, fontWeight: FontWeight.w700)),
                              subtitle: Text(s, style: TextStyle(color: widget.muted, fontSize: 11)),
                              onTap: () => Navigator.pop(ctx, s),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
    if (picked != null) {
      setState(() => _symbol = picked);
      _loadCandles(fit: true);
    }
  }

  Widget _chip(String label, bool selected, VoidCallback onTap) => Padding(
        padding: const EdgeInsetsDirectional.only(end: 6),
        child: ChoiceChip(
          label: Text(label, style: const TextStyle(fontSize: 11)),
          selected: selected,
          onSelected: (_) => onTap(),
          visualDensity: VisualDensity.compact,
        ),
      );

  @override
  Widget build(BuildContext context) {
    final indicatorLabels = {
      'volume': t('الحجم', 'Volume'),
      'ema': 'EMA 20/50',
      'bb': 'Bollinger',
      'vwap': 'VWAP',
      'rsi': 'RSI',
      'macd': 'MACD',
    };

    final chartBody = Column(
      children: [
        if (!widget.embedded)
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(10, 8, 10, 0),
            child: Row(
              children: [
                for (final m in _markets)
                  _chip(m.toUpperCase(), _market == m, () {
                    setState(() {
                      _market = m;
                      _symbols = [];
                      _symbol = 'BTCUSDT';
                      if (!_availableIntervals.contains(_interval)) {
                        _interval = '5m';
                      }
                    });
                    _loadSymbols();
                    _loadCandles(fit: true);
                  }),
                const SizedBox(width: 10),
                for (final i in _availableIntervals)
                  _chip(i, _interval == i, () {
                    setState(() => _interval = i);
                    _loadCandles(fit: true);
                  }),
              ],
            ),
          )
        else if (widget.lockSelection)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '${_symbol} • ${_market.toUpperCase()} • ${_interval}',
                    style: TextStyle(color: widget.text, fontWeight: FontWeight.w800),
                  ),
                ),
                const Icon(Icons.lock_outline, size: 15, color: _up),
              ],
            ),
          )
        else
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(10, 8, 10, 0),
            child: Row(
              children: [
                TextButton.icon(
                  onPressed: _pickSymbol,
                  icon: const Icon(Icons.swap_horiz, size: 17),
                  label: Text(_symbol.isEmpty ? t('اختر العملة', 'Select asset') : (_symbolNames[_symbol] ?? _symbol)),
                ),
                const SizedBox(width: 8),
                for (final i in _availableIntervals)
                  _chip(i, _interval == i, () {
                    setState(() => _interval = i);
                    _loadCandles(fit: true);
                  }),
              ],
            ),
          ),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.fromLTRB(10, 2, 10, 4),
          child: Row(
            children: [
              for (final entry in indicatorLabels.entries)
                Padding(
                  padding: const EdgeInsetsDirectional.only(end: 6),
                  child: FilterChip(
                    label: Text(entry.value, style: const TextStyle(fontSize: 11)),
                    selected: _indicators[entry.key] ?? false,
                    visualDensity: VisualDensity.compact,
                    onSelected: (v) {
                      setState(() => _indicators[entry.key] = v);
                      _pushIndicators();
                    },
                  ),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
          child: Row(
            children: [
              Text(
                _lastPrice == null ? '—' : _lastPrice!.toStringAsPrecision(8),
                style: TextStyle(
                  color: widget.text,
                  fontWeight: FontWeight.w900,
                  fontSize: 16,
                ),
              ),
              const Spacer(),
              if (_error != null)
                Flexible(
                  child: Text(
                    t('تعذّر التحديث', 'Update failed'),
                    style: const TextStyle(color: _down, fontSize: 10),
                  ),
                ),
            ],
          ),
        ),
        if (widget.showSubmitButton)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _submitting ? null : _submitToAgent,
                icon: const Icon(Icons.psychology_alt, size: 18),
                label: Text(_submitting
                    ? t('جارٍ التحليل...', 'ANALYZING...')
                    : t('إرسال للوكيل', 'SEND TO AGENT')),
              ),
            ),
          ),
        if (widget.showSubmitButton)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _scalpingBusy ? null : _analyzeScalpingV2,
                icon: const Icon(Icons.bolt, size: 18),
                label: Text(_scalpingBusy
                    ? t('جارٍ فحص السوق...', 'CHECKING LIVE MARKET...')
                    : t('تحليل Scalping v2', 'ANALYZE SCALPING v2')),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsetsDirectional.only(start: 8, end: 8, bottom: 3),
          child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            IconButton(tooltip: t('تكبير', 'Zoom in'), visualDensity: VisualDensity.compact,
              onPressed: () => _chartZoom(0.72), icon: const Icon(Icons.add_circle_outline, size: 21)),
            IconButton(tooltip: t('تصغير', 'Zoom out'), visualDensity: VisualDensity.compact,
              onPressed: () => _chartZoom(1.38), icon: const Icon(Icons.remove_circle_outline, size: 21)),
            IconButton(tooltip: t('ملاءمة كامل التشارت', 'Fit chart'), visualDensity: VisualDensity.compact,
              onPressed: _fitChart, icon: const Icon(Icons.fit_screen, size: 19)),
          ]),
        ),
        Expanded(
          child: WebViewWidget(
            controller: _controller,
            gestureRecognizers: <Factory<OneSequenceGestureRecognizer>>{
              Factory<OneSequenceGestureRecognizer>(() => EagerGestureRecognizer()),
            },
          ),
        ),
      ],
    );

    if (widget.embedded) {
      return Directionality(
        textDirection: widget.english ? TextDirection.ltr : TextDirection.rtl,
        child: SizedBox(height: 540, child: chartBody),
      );
    }

    return Directionality(
      textDirection: widget.english ? TextDirection.ltr : TextDirection.rtl,
      child: Scaffold(
        backgroundColor: widget.bg,
        appBar: AppBar(
          backgroundColor: widget.panel,
          foregroundColor: widget.text,
          title: Text(t('التشارت الاحترافي', 'Pro Chart')),
          actions: [
            TextButton.icon(
              onPressed: _pickSymbol,
              icon: const Icon(Icons.swap_horiz, size: 18),
              label: Text(_symbol),
            ),
          ],
        ),
        body: chartBody,
      ),
    );
  }
}

class AgentSubmissionScreen extends StatefulWidget {
  final bool english;
  final Color bg, panel, text, muted;
  final String domain, symbol, timeframe;
  final double? initialPrice;

  const AgentSubmissionScreen({
    super.key,
    required this.english,
    required this.bg,
    required this.panel,
    required this.text,
    required this.muted,
    required this.domain,
    required this.symbol,
    required this.timeframe,
    this.initialPrice,
  });

  @override
  State<AgentSubmissionScreen> createState() => _AgentSubmissionScreenState();
}

class _AgentSubmissionScreenState extends State<AgentSubmissionScreen> {
  late final TextEditingController _entry;
  final TextEditingController _target = TextEditingController();
  final TextEditingController _stop = TextEditingController();
  bool _sending = false;
  bool _requestSubmitted = false;
  bool _requestReceived = false;
  String? _requestId;
  Map<String, dynamic>? _result;
  String? _error;

  String t(String ar, String en) => widget.english ? en : ar;

  @override
  void initState() {
    super.initState();
    _entry = TextEditingController(
      text: widget.initialPrice == null ? '' : widget.initialPrice!.toString(),
    );
  }

  @override
  void dispose() {
    _entry.dispose();
    _target.dispose();
    _stop.dispose();
    super.dispose();
  }

  double? _number(TextEditingController controller) =>
      double.tryParse(controller.text.trim());

  Future<void> _submit() async {
    final entry = _number(_entry);
    final target = _number(_target);
    final stop = _number(_stop);
    if (entry == null || target == null || stop == null ||
        !entry.isFinite || !target.isFinite || !stop.isFinite ||
        entry <= 0 || target <= 0 || stop <= 0) {
      setState(() => _error = t(
        'أدخل أسعاراً رقمية صحيحة وأكبر من صفر في الخانات الثلاث.',
        'Enter valid positive numeric prices in all three fields.',
      ));
      return;
    }
    setState(() {
      _sending = true;
      _requestSubmitted = true;
      _requestReceived = false;
      _requestId = null;
      _error = null;
      _result = null;
    });
    try {
      final acknowledgement = await ApiService.submitChartSignal(
        domain: widget.domain,
        symbol: widget.symbol,
        timeframe: widget.timeframe,
        entryPrice: entry,
        takeProfit: target,
        stopLoss: stop,
      );
      final requestId = '${acknowledgement['request_id'] ?? ''}';
      if (acknowledgement['request_status'] != 'RECEIVED' || requestId.isEmpty) {
        throw Exception(t(
          'لم يؤكد الخادم استلام الطلب.',
          'The server did not confirm receipt of the request.',
        ));
      }
      if (mounted) {
        setState(() {
          _requestReceived = true;
          _requestId = requestId;
        });
      }

      Map<String, dynamic>? decision;
      Object? lastPollingError;
      String? processingFailure;
      // Keep waiting through brief mobile-network interruptions; one failed poll
      // must not erase the server's acknowledgement or the pending request.
      for (var attempt = 0; attempt < 90; attempt++) {
        await Future.delayed(const Duration(seconds: 2));
        if (!mounted) return;
        try {
          final progress = await ApiService.agentSubmissionStatus(requestId);
          final requestStatus = '${progress['request_status'] ?? ''}'.toUpperCase();
          if (requestStatus == 'COMPLETED' && progress['result'] is Map) {
            decision = Map<String, dynamic>.from(progress['result'] as Map);
            break;
          }
          if (requestStatus == 'FAILED') {
            final failedResult = progress['result'];
            processingFailure = '${(failedResult is Map ? failedResult['decision_reason'] ?? failedResult['reason'] : null) ?? progress['reason'] ?? progress['message'] ?? 'Agent processing failed'}';
            break;
          }
          if (requestStatus == 'NOT_FOUND') {
            processingFailure = '${progress['reason'] ?? 'The request could not be found on the server'}';
            break;
          }
          lastPollingError = null;
        } catch (error) {
          lastPollingError = error;
          // Retry transient transport errors until the full wait window expires.
        }
      }
      if (processingFailure != null) {
        throw Exception(
          '${t('حدث خطأ تقني أثناء معالجة الطلب، وليس رفضاً للفرصة: ', 'A technical error occurred while processing the request; this is not a trade rejection: ')}'
          '$processingFailure • Request ID: $requestId',
        );
      }
      if (decision == null) {
        throw Exception(
          '${t('لم يصل قرار الوكيل خلال المهلة. رقم الطلب: ', 'No agent decision arrived before timeout. Request ID: ')}'
          '${requestId}'
          '${lastPollingError == null ? '' : ' • $lastPollingError'}',
        );
      }
      if (mounted) setState(() => _result = decision);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Widget _priceField(String label, TextEditingController controller, Color accent) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TextField(
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: false),
          style: TextStyle(color: widget.text, fontWeight: FontWeight.w700),
          decoration: InputDecoration(
            labelText: label,
            labelStyle: TextStyle(color: widget.muted),
            prefixIcon: Icon(Icons.price_change_outlined, color: accent),
            filled: true,
            fillColor: widget.panel,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: BorderSide(color: accent.withOpacity(.25)),
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final status = '${_result == null ? 'PROCESSING' : (_result!['decision_status'] ?? (_result!['opened'] == true ? 'APPROVED' : 'REJECTED'))}'.toUpperCase();
    final approved = status == 'APPROVED';
    final waiting = status == 'WAIT' || status == 'PROCESSING';
    final decisionColor = approved ? _up : waiting ? const Color(0xFFFFC857) : _down;
    final direction = _result?['signal'] is Map
        ? ((_result!['signal'] as Map)['direction'] ?? '—')
        : '—';
    final reason = _result?['decision_reason'] ??
        _result?['reason'] ??
        (_result?['execution'] is Map ? (_result!['execution'] as Map)['reason'] : null);

    return Directionality(
      textDirection: widget.english ? TextDirection.ltr : TextDirection.rtl,
      child: Scaffold(
        backgroundColor: widget.bg,
        appBar: AppBar(
          backgroundColor: widget.panel,
          foregroundColor: widget.text,
          title: Text(t('إرسال فرصة للوكيل', 'SUBMIT SETUP TO AGENT')),
        ),
        body: ListView(
          padding: const EdgeInsets.all(14),
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: widget.panel,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: _up.withOpacity(.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.candlestick_chart, color: _up, size: 26),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.symbol, style: TextStyle(
                          color: widget.text, fontWeight: FontWeight.w900, fontSize: 18,
                        )),
                        Text('${widget.domain.toUpperCase()} • ${widget.timeframe}',
                          style: TextStyle(color: widget.muted, fontSize: 11)),
                      ],
                    ),
                  ),
                  const Icon(Icons.lock_outline, color: _up),
                ],
              ),
            ),
            const SizedBox(height: 14),
            _priceField(t('سعر الدخول المقترح', 'PROPOSED ENTRY'), _entry, const Color(0xFF4287F5)),
            _priceField(t('سعر جني الأرباح', 'TAKE PROFIT'), _target, _up),
            _priceField(t('سعر وقف الخسارة', 'STOP LOSS'), _stop, _down),
            Text(
              t('الاتجاه لا تختاره أنت؛ الوكيل يحدده وفق تحليله. إدخال الأسعار لا يفتح صفقة بحد ذاته.',
                'You do not choose direction; the agent determines it. Entering prices alone never opens a trade.'),
              style: TextStyle(color: widget.muted, fontSize: 11, height: 1.5),
            ),
            const SizedBox(height: 12),
            Text(t('التشارت الحي للمراجعة', 'LIVE CHART REVIEW'),
              style: TextStyle(color: widget.text, fontWeight: FontWeight.w900)),
            const SizedBox(height: 6),
            ProChartScreen(
              key: ValueKey('review-${widget.domain}-${widget.symbol}-${widget.timeframe}'),
              english: widget.english,
              bg: widget.bg,
              panel: widget.panel,
              text: widget.text,
              muted: widget.muted,
              positions: const [],
              initialSymbol: widget.symbol,
              initialMarket: widget.domain,
              initialInterval: widget.timeframe,
              embedded: true,
              showSubmitButton: false,
              lockSelection: true,
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 50,
              child: FilledButton.icon(
                onPressed: _sending ? null : _submit,
                icon: _sending
                    ? const SizedBox(width: 18, height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.psychology_alt),
                label: Text(_sending
                    ? t('الوكيل يحلل الفرصة...', 'AGENT ANALYZING...')
                    : t('إرسال للتحليل واتخاذ القرار', 'SEND FOR AGENT DECISION')),
              ),
            ),
            if (_requestSubmitted || _requestReceived) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(13),
                decoration: BoxDecoration(color: widget.panel, borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: (_error != null ? const Color(0xFFFFC857) : _result == null ? const Color(0xFF4287F5) : (_result!['decision_status'] == 'APPROVED' ? _up : _down)).withOpacity(.45))),
                child: Row(children: [
                  if (_result == null && _error == null && _sending)
                    const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  else
                    Icon(
                      _error != null ? Icons.error_outline :
                      (_result == null ? Icons.mark_email_read_outlined : Icons.verified),
                      color: _error != null ? const Color(0xFFFFC857) : decisionColor,
                      size: 20,
                    ),
                  const SizedBox(width: 10),
                  Expanded(child: Text(
                    '${_error != null ? _error! : _result != null ? t('وصل قرار الوكيل.', 'Agent decision received.') : _requestReceived ? t('تم استلام الطلب من الخادم وإرساله للوكيل المختص. يجري التحليل الآن.', 'Server confirmed receipt and forwarded the request to the selected agent. Analysis is running.') : t('جارٍ إرسال الطلب إلى الخادم...', 'Sending request to server...')}'
                    '${_requestId == null ? '' : '\\nRequest ID: $_requestId'}',
                    style: TextStyle(color: widget.text, fontSize: 12, height: 1.45))),
                ]),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 10),
              Text(_error!, style: const TextStyle(color: _down, fontSize: 12)),
            ],
            if (_result != null) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: widget.panel,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: decisionColor.withOpacity(.45)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Icon(
                        approved ? Icons.check_circle : waiting ? Icons.hourglass_top : Icons.cancel,
                        color: decisionColor,
                      ),
                      const SizedBox(width: 8),
                      Expanded(child: Text(
                        status.isEmpty ? t('لم يصدر قرار', 'NO DECISION') : status,
                        style: TextStyle(color: decisionColor,
                          fontWeight: FontWeight.w900, fontSize: 16),
                      )),
                      Text('${direction}', style: TextStyle(
                        color: widget.text, fontWeight: FontWeight.bold)),
                    ]),
                    const SizedBox(height: 8),
                    Text('${reason ?? t('لم يذكر الوكيل سبباً إضافياً.', 'No additional reason returned.')}',
                      style: TextStyle(color: widget.text, height: 1.5)),
                    if (_result!['trade_plan'] is Map) ...[
                      const SizedBox(height: 10),
                      Text('Entry: ${(_result!['trade_plan'] as Map)['entry'] ?? '—'}',
                        style: TextStyle(color: widget.text)),
                      Text('TP: ${(_result!['trade_plan'] as Map)['take_profit'] ?? '—'}',
                        style: const TextStyle(color: _up)),
                      Text('SL: ${(_result!['trade_plan'] as Map)['stop_loss'] ?? '—'}',
                        style: const TextStyle(color: _down)),
                      Text('R/R: ${(_result!['trade_plan'] as Map)['reward_risk'] ?? '—'}',
                        style: TextStyle(color: widget.text)),
                    ],
                    if (_result!['opened'] == true)
                      Padding(
                        padding: const EdgeInsets.only(top: 10),
                        child: Text(
                          t('تم قبول الفرصة وفتح مركز DEMO بعد اجتياز فحوصات المخاطر.',
                            'Setup accepted; a DEMO position opened after risk checks.'),
                          style: const TextStyle(color: _up, fontWeight: FontWeight.bold),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

const String _chartHtml = r'''
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<style>
  html, body { margin:0; padding:0; height:100%; background:#0d1117; overflow:hidden; }
  #c { position:absolute; inset:0; touch-action:none; }
</style>
<script src="https://unpkg.com/lightweight-charts@5.0.0/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>
<div id="c"></div>
<script>
var LW = LightweightCharts;
var chart = LW.createChart(document.getElementById('c'), {
  autoSize: true,
  layout: { background: { type: 'solid', color: '#0d1117' }, textColor: '#c9d1d9' },
  grid: { vertLines: { color: '#1c2128' }, horzLines: { color: '#1c2128' } },
  crosshair: { mode: 0 },
  handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
  handleScale: {
    axisPressedMouseMove: { time: true, price: true },
    axisDoubleClickReset: true, mouseWheel: true, pinch: true
  },
  rightPriceScale: { borderColor: '#2b3139', autoScale: true },
  timeScale: { borderColor: '#2b3139', timeVisible: true, secondsVisible: false }
});
var candle = chart.addSeries(LW.CandlestickSeries, {
  upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
  wickUpColor: '#26a69a', wickDownColor: '#ef5350'
});
var volume = chart.addSeries(LW.HistogramSeries, {
  priceFormat: { type: 'volume' }, priceScaleId: ''
});
volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

var data = [];
var extra = [];       // indicator series currently on the chart
var lines = [];       // trade price lines
var tradeMarkers = null;
var flags = { volume: true, ema: true, bb: false, vwap: false, rsi: false, macd: false };
var lastLevels = [];

function line(color, width) {
  return { color: color, lineWidth: width || 1, priceLineVisible: false, lastValueVisible: false };
}
function pts(values) {
  var out = [];
  for (var i = 0; i < data.length; i++) {
    if (values[i] !== null && values[i] !== undefined && isFinite(values[i])) {
      out.push({ time: data[i].time, value: values[i] });
    }
  }
  return out;
}
function ema(vals, p) {
  var k = 2 / (p + 1), out = [], prev = null;
  for (var i = 0; i < vals.length; i++) {
    if (i < p - 1) { out.push(null); continue; }
    if (prev === null) {
      var s = 0; for (var j = i - p + 1; j <= i; j++) s += vals[j];
      prev = s / p;
    } else { prev = vals[i] * k + prev * (1 - k); }
    out.push(prev);
  }
  return out;
}
function sma(vals, p) {
  var out = [];
  for (var i = 0; i < vals.length; i++) {
    if (i < p - 1) { out.push(null); continue; }
    var s = 0; for (var j = i - p + 1; j <= i; j++) s += vals[j];
    out.push(s / p);
  }
  return out;
}
function rsi(vals, p) {
  var out = [null], g = 0, l = 0;
  for (var i = 1; i < vals.length; i++) {
    var d = vals[i] - vals[i - 1], up = d > 0 ? d : 0, dn = d < 0 ? -d : 0;
    if (i <= p) {
      g += up; l += dn;
      if (i === p) { g /= p; l /= p; out.push(l === 0 ? 100 : 100 - 100 / (1 + g / l)); }
      else out.push(null);
    } else {
      g = (g * (p - 1) + up) / p; l = (l * (p - 1) + dn) / p;
      out.push(l === 0 ? 100 : 100 - 100 / (1 + g / l));
    }
  }
  return out;
}
function closes() { return data.map(function (c) { return c.close; }); }

function clearExtra() {
  for (var i = 0; i < extra.length; i++) { try { chart.removeSeries(extra[i]); } catch (e) {} }
  extra = [];
}
function add(type, opts, pane) {
  var s = chart.addSeries(type, opts, pane);
  extra.push(s);
  return s;
}
function drawIndicators() {
  clearExtra();
  volume.applyOptions({ visible: !!flags.volume });
  if (!data.length) return;
  var c = closes(), pane = 1;
  if (flags.ema) {
    add(LW.LineSeries, line('#f0b90b', 1)).setData(pts(ema(c, 20)));
    add(LW.LineSeries, line('#39a8ff', 1)).setData(pts(ema(c, 50)));
  }
  if (flags.bb) {
    var mid = sma(c, 20), up = [], lo = [];
    for (var i = 0; i < c.length; i++) {
      if (mid[i] === null) { up.push(null); lo.push(null); continue; }
      var v = 0; for (var j = i - 19; j <= i; j++) v += Math.pow(c[j] - mid[i], 2);
      var sd = Math.sqrt(v / 20);
      up.push(mid[i] + 2 * sd); lo.push(mid[i] - 2 * sd);
    }
    add(LW.LineSeries, line('#9b72ff', 1)).setData(pts(up));
    add(LW.LineSeries, line('#6b7280', 1)).setData(pts(mid));
    add(LW.LineSeries, line('#9b72ff', 1)).setData(pts(lo));
  }
  if (flags.vwap) {
    var pv = 0, vv = 0, out = [];
    for (var k = 0; k < data.length; k++) {
      var tp = (data[k].high + data[k].low + data[k].close) / 3, vol = data[k].volume || 0;
      pv += tp * vol; vv += vol; out.push(vv > 0 ? pv / vv : null);
    }
    add(LW.LineSeries, line('#ff9800', 2)).setData(pts(out));
  }
  if (flags.rsi) {
    var r = add(LW.LineSeries, line('#c084fc', 2), pane);
    r.setData(pts(rsi(c, 14)));
    r.createPriceLine({ price: 70, color: '#6b7280', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' });
    r.createPriceLine({ price: 30, color: '#6b7280', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' });
    pane++;
  }
  if (flags.macd) {
    var e12 = ema(c, 12), e26 = ema(c, 26), m = [];
    for (var a = 0; a < c.length; a++) m.push(e12[a] !== null && e26[a] !== null ? e12[a] - e26[a] : null);
    var firstIdx = m.findIndex(function (x) { return x !== null; });
    var sig = new Array(c.length).fill(null);
    if (firstIdx >= 0) {
      var tail = ema(m.slice(firstIdx).map(function (x) { return x; }), 9);
      for (var b = 0; b < tail.length; b++) sig[firstIdx + b] = tail[b];
    }
    var hist = [];
    for (var h = 0; h < c.length; h++) {
      if (m[h] === null || sig[h] === null) continue;
      var val = m[h] - sig[h];
      hist.push({ time: data[h].time, value: val, color: val >= 0 ? '#26a69a' : '#ef5350' });
    }
    add(LW.HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane).setData(hist);
    add(LW.LineSeries, line('#39a8ff', 1), pane).setData(pts(m));
    add(LW.LineSeries, line('#ff9800', 1), pane).setData(pts(sig));
    pane++;
  }
  try {
    var panes = chart.panes();
    for (var p = 1; p < panes.length; p++) panes[p].setHeight(110);
  } catch (e) {}
}
function setCandles(arr, fit) {
  data = arr.map(function (x) {
    return { time: x.time, open: x.open, high: x.high, low: x.low, close: x.close, volume: x.volume };
  });
  candle.setData(data);
  volume.setData(data.map(function (x) {
    return { time: x.time, value: x.volume, color: x.close >= x.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' };
  }));
  drawIndicators();
  if (fit) chart.timeScale().fitContent();
}
function zoomTimeScale(factor) {
  var range = chart.timeScale().getVisibleLogicalRange();
  if (!range) return;
  var center = (range.from + range.to) / 2;
  var half = Math.max(3, (range.to - range.from) * factor / 2);
  chart.timeScale().setVisibleLogicalRange({ from: center - half, to: center + half });
}
function resetChartView() {
  chart.timeScale().fitContent();
  candle.priceScale().applyOptions({ autoScale: true });
}
function setIndicators(f) { flags = f; drawIndicators(); }
function setTradeMarkers(markers) {
  try {
    if (tradeMarkers) tradeMarkers.setMarkers([]);
    tradeMarkers = LW.createSeriesMarkers(candle, markers || []);
  } catch (e) {
    console.log('Trade marker rendering unavailable', e);
  }
}
function setLevels(levels) {
  for (var i = 0; i < lines.length; i++) { try { candle.removePriceLine(lines[i]); } catch (e) {} }
  lines = [];
  for (var j = 0; j < levels.length; j++) {
    var l = levels[j];
    lines.push(candle.createPriceLine({
      price: l.price, color: l.color, lineWidth: 2,
      lineStyle: l.title.indexOf('ENTRY') === 0 ? 0 : 2,
      axisLabelVisible: true, title: l.title
    }));
  }
}
</script>
</body>
</html>
''';
