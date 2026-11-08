import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../services/api_service.dart';

const _up = Color(0xFF26A69A);
const _down = Color(0xFFEF5350);

/// Professional candlestick chart (TradingView Lightweight Charts in a WebView)
/// with indicators and the entry / stop-loss / take-profit lines of open trades.
class ProChartScreen extends StatefulWidget {
  final bool english;
  final Color bg, panel, text, muted;
  final List<Map<String, dynamic>> positions;
  final String initialSymbol;

  const ProChartScreen({
    super.key,
    required this.english,
    required this.bg,
    required this.panel,
    required this.text,
    required this.muted,
    required this.positions,
    this.initialSymbol = 'BTCUSDT',
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
  String? _error;
  String _market = 'futures';
  late String _symbol;
  String _interval = '5m';
  List<String> _symbols = [];
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
    if (_market == 'spot') return ['5m', '15m', '1h', '4h'];
    return ['5m', '15m', '1h'];
  }
  static const _markets = ['futures', 'spot', 'alpha'];

  String t(String ar, String en) => widget.english ? en : ar;

  @override
  void initState() {
    super.initState();
    _symbol = widget.initialSymbol;
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
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _loadSymbols() async {
    try {
      final result = await ApiService.marketSymbols(_market);
      final raw = result['symbols'];
      final list = <String>[];
      if (raw is List) {
        for (final item in raw) {
          if (item is String) {
            list.add(item);
          } else if (item is Map && item['symbol'] != null) {
            list.add('${item['symbol']}');
          }
        }
      }
      if (mounted && list.isNotEmpty) {
        setState(() => _symbols = list..sort());
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
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
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
      add('take_profit', 'TP', '#26a69a');
    }
    _controller.runJavaScript('setLevels(${jsonEncode(levels)});');
  }

  void _pushIndicators() {
    if (!_pageReady) return;
    _controller.runJavaScript('setIndicators(${jsonEncode(_indicators)});');
  }

  Future<void> _submitToAgent() async {
    if (_submitting) return;
    setState(() => _submitting = true);
    final domain = _market;
    try {
      final result = await ApiService.submitChartSignal(
        domain: domain,
        symbol: _symbol,
        timeframe: _interval,
      );
      if (!mounted) return;
      final signal = result['signal'] is Map
          ? Map<String, dynamic>.from(result['signal'] as Map)
          : <String, dynamic>{};
      final plan = result['trade_plan'] is Map
          ? Map<String, dynamic>.from(result['trade_plan'] as Map)
          : <String, dynamic>{};
      final safety = result['token_safety'] is Map
          ? Map<String, dynamic>.from(result['token_safety'] as Map)
          : <String, dynamic>{};
      final confidence = signal['confidence'];
      final reason = signal['reason'] ?? plan['reason'] ?? '';
      final execution = result['execution'] is Map
          ? Map<String, dynamic>.from(result['execution'] as Map)
          : <String, dynamic>{};
      if (result['opened'] == true && execution['position_id'] != null) {
        final id = '${execution['position_id']}';
        if (!widget.positions.any((p) => '${p['position_id']}' == id)) {
          widget.positions.add(execution);
          _pushLevels();
        }
      }
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: widget.panel,
          title: Text(t('نتيجة تحليل الوكيل', 'Agent analysis result'),
              style: TextStyle(color: widget.text)),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('${_symbol} • ${domain.toUpperCase()} • ${_interval}',
                    style: TextStyle(color: widget.text, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text('${result['decision'] ?? result['reason'] ?? 'No decision'}',
                    style: TextStyle(color: widget.text)),
                Text('${t('الاتجاه', 'Direction')}: ${signal['direction'] ?? '—'}',
                    style: TextStyle(color: widget.text)),
                Text('${t('الثقة', 'Confidence')}: ${confidence ?? '—'}%',
                    style: TextStyle(color: widget.text)),
                if (plan.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('Entry: ${plan['entry'] ?? '—'}',
                      style: TextStyle(color: widget.text)),
                  Text('SL: ${plan['stop_loss'] ?? '—'}',
                      style: const TextStyle(color: _down)),
                  Text('TP: ${plan['take_profit'] ?? '—'}',
                      style: const TextStyle(color: _up)),
                  Text('R/R: ${plan['reward_risk'] ?? '—'}',
                      style: TextStyle(color: widget.text)),
                ],
                if (domain == 'alpha')
                  Text('Token safety: ${safety['status'] ?? 'UNKNOWN'}',
                      style: TextStyle(color: widget.text)),
                if (reason.toString().isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(reason.toString(),
                      style: TextStyle(color: widget.muted, fontSize: 12)),
                ],
                const SizedBox(height: 10),
                Text(
                  result['opened'] == true
                      ? t('وافق الوكيل وفتح صفقة DEMO بعد اجتياز فحوصات المخاطر.',
                          'Agent approved and opened a DEMO position after risk checks.')
                      : t('لم تُفتح صفقة؛ قرار الوكيل أو فحوصات المخاطر رفضت الدخول.',
                          'No position opened; the agent or backend risk checks rejected entry.'),
                  style: TextStyle(
                    color: result['opened'] == true ? _up : widget.muted,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text(t('إغلاق', 'Close')),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${t('تعذر إرسال التحليل: ', 'Agent request failed: ')}$e')),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
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
                .where((s) => s.toUpperCase().contains(filter.toUpperCase()))
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
                              title: Text(
                                s,
                                style: TextStyle(color: widget.text),
                              ),
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
        body: Column(
          children: [
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
                        if (m == 'futures' || m == 'spot') {
                          _symbol = 'BTCUSDT';
                        }
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
                        label: Text(entry.value,
                            style: const TextStyle(fontSize: 11)),
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
              padding: const EdgeInsets.symmetric(horizontal: 14),
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
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _submitting ? null : _submitToAgent,
                  icon: const Icon(Icons.psychology_alt, size: 18),
                  label: Text(_submitting ? t('جارٍ التحليل...', 'ANALYZING...') : t('إرسال للوكيل', 'SEND TO AGENT')),
                ),
              ),
            ),
            Expanded(child: WebViewWidget(controller: _controller)),
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
  #c { position:absolute; inset:0; }
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
  rightPriceScale: { borderColor: '#2b3139' },
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
function setIndicators(f) { flags = f; drawIndicators(); }
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
