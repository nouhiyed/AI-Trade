import 'package:flutter/material.dart';
import '../services/api_service.dart';

double? _price(dynamic value) {
  final parsed = double.tryParse('${value ?? ''}');
  return parsed != null && parsed.isFinite && parsed > 0 ? parsed : null;
}

class HistoricalTradeChartPainter extends CustomPainter {
  final List<Map<String, dynamic>> candles;
  final String symbol, direction, timeframe;
  final double? entry, exit, stopLoss, takeProfit;
  final int? entryTime, exitTime;

  HistoricalTradeChartPainter({
    required this.candles,
    required this.symbol,
    required this.direction,
    required this.timeframe,
    required this.entry,
    required this.exit,
    required this.stopLoss,
    required this.takeProfit,
    required this.entryTime,
    required this.exitTime,
  });

  static const Color up = Color(0xFF26A69A);
  static const Color down = Color(0xFFEF5350);
  static const Color entryColor = Color(0xFF4287F5);
  static const Color exitColor = Color(0xFFF5A623);
  static const Color grid = Color(0xFF252D39);
  static const Color foreground = Color(0xFFD5DEEA);

  void _text(Canvas canvas, String value, Offset offset, Color color, {double size = 10}) {
    final painter = TextPainter(
      text: TextSpan(text: value, style: TextStyle(
        color: color, fontSize: size, fontWeight: FontWeight.w700,
      )),
      textDirection: TextDirection.ltr,
      maxLines: 1,
    )..layout(maxWidth: 150);
    painter.paint(canvas, offset);
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.isEmpty || size.width <= 0 || size.height <= 0) return;
    const left = 10.0, right = 105.0, top = 34.0, bottom = 25.0;
    final plotW = size.width - left - right;
    final plotH = size.height - top - bottom;
    if (plotW <= 0 || plotH <= 0) return;

    final values = <double>[];
    for (final candle in candles) {
      for (final key in ['high', 'low']) {
        final value = _price(candle[key]);
        if (value != null) values.add(value);
      }
    }
    for (final value in [entry, exit, stopLoss, takeProfit]) {
      if (value != null) values.add(value);
    }
    if (values.isEmpty) return;
    var minPrice = values.reduce((a, b) => a < b ? a : b);
    var maxPrice = values.reduce((a, b) => a > b ? a : b);
    final padding = (maxPrice - minPrice) * .06;
    minPrice -= padding == 0 ? minPrice * .001 : padding;
    maxPrice += padding == 0 ? maxPrice * .001 : padding;

    double y(double price) => top + (maxPrice - price) / (maxPrice - minPrice) * plotH;
    final gridPaint = Paint()..color = grid..strokeWidth = 1;
    for (var i = 0; i <= 5; i++) {
      final gy = top + plotH * i / 5;
      canvas.drawLine(Offset(left, gy), Offset(left + plotW, gy), gridPaint);
      final price = maxPrice - (maxPrice - minPrice) * i / 5;
      _text(canvas, price.toStringAsPrecision(6), Offset(left + plotW + 5, gy - 6), foreground, size: 8);
    }

    final step = plotW / candles.length;
    final bodyWidth = (step * .62).clamp(1.0, 9.0).toDouble();
    final wickPaint = Paint()..strokeWidth = 1;
    for (var i = 0; i < candles.length; i++) {
      final c = candles[i];
      final o = _price(c['open']), h = _price(c['high']);
      final l = _price(c['low']), close = _price(c['close']);
      if (o == null || h == null || l == null || close == null) continue;
      final x = left + step * (i + .5);
      final color = close >= o ? up : down;
      wickPaint.color = color;
      canvas.drawLine(Offset(x, y(h)), Offset(x, y(l)), wickPaint);
      final topBody = y(o) < y(close) ? y(o) : y(close);
      final bottomBody = y(o) > y(close) ? y(o) : y(close);
      final rect = Rect.fromLTRB(
        x - bodyWidth / 2, topBody, x + bodyWidth / 2,
        bottomBody > topBody ? bottomBody : topBody + 1,
      );
      canvas.drawRect(rect, Paint()..color = color);
    }

    void level(String label, double? price, Color color) {
      if (price == null) return;
      final py = y(price);
      final paint = Paint()..color = color..strokeWidth = 1.7;
      canvas.drawLine(Offset(left, py), Offset(left + plotW, py), paint);
      final labelRect = Rect.fromLTWH(left + plotW + 2, py - 8, right - 7, 16);
      canvas.drawRect(labelRect, Paint()..color = color);
      _text(canvas, '$label ${price.toStringAsPrecision(7)}',
        Offset(left + plotW + 5, py - 5), Colors.white, size: 8);
    }

    _text(canvas, '$symbol  $direction  $timeframe',
      const Offset(left, 8), foreground, size: 11);
    level('TP', takeProfit, up);
    level('ENTRY', entry, entryColor);
    level('EXIT', exit, exitColor);
    level('SL', stopLoss, down);

    // Place markers on the actual entry/exit candles using their timestamps.
    int nearestIndex(int? timestamp) {
      if (timestamp == null || candles.isEmpty) return -1;
      var bestIndex = -1;
      var bestDistance = 1 << 62;
      for (var i = 0; i < candles.length; i++) {
        final raw = candles[i]['time'];
        final time = raw is num ? raw.toInt() : int.tryParse('$raw');
        if (time == null) continue;
        final distance = (time - timestamp).abs();
        if (distance < bestDistance) {
          bestDistance = distance;
          bestIndex = i;
        }
      }
      return bestIndex;
    }

    final entryIndex = nearestIndex(entryTime);
    final exitIndex = nearestIndex(exitTime);
    Offset? markerPoint(int index, double? price) {
      if (index < 0 || price == null) return null;
      return Offset(left + step * (index + .5), y(price));
    }

    final entryPoint = markerPoint(entryIndex, entry);
    final exitPoint = markerPoint(exitIndex, exit);
    if (entryPoint != null && exitPoint != null) {
      final connector = Paint()
        ..color = const Color(0xFFB18CFF)
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke;
      final path = Path()..moveTo(entryPoint.dx, entryPoint.dy)..lineTo(exitPoint.dx, exitPoint.dy);
      canvas.drawPath(
        path,
        connector..strokeCap = StrokeCap.round,
      );
    }

    void marker(Offset? point, Color color, bool upward, String label) {
      if (point == null) return;
      final direction = upward ? -1.0 : 1.0;
      final triangle = Path()
        ..moveTo(point.dx, point.dy + direction * 13)
        ..lineTo(point.dx - 7, point.dy - direction * 1)
        ..lineTo(point.dx + 7, point.dy - direction * 1)
        ..close();
      canvas.drawPath(triangle, Paint()..color = color);
      canvas.drawCircle(point, 3, Paint()..color = Colors.white);
      _text(canvas, label, Offset(point.dx + 7, point.dy + (upward ? -20 : 7)), color, size: 9);
    }

    marker(entryPoint, entryColor, direction != 'SHORT', 'ENTRY');
    marker(exitPoint, exitColor, direction == 'SHORT', 'EXIT');
  }

  @override
  bool shouldRepaint(covariant HistoricalTradeChartPainter oldDelegate) => true;
}

class ClosedTradeDetailScreen extends StatefulWidget {
  final Map<String, dynamic> trade;
  final bool english;
  final Color bg, panel, text, muted;

  const ClosedTradeDetailScreen({
    super.key,
    required this.trade,
    required this.english,
    required this.bg,
    required this.panel,
    required this.text,
    required this.muted,
  });

  @override
  State<ClosedTradeDetailScreen> createState() => _ClosedTradeDetailScreenState();
}

class _ClosedTradeDetailScreenState extends State<ClosedTradeDetailScreen> {
  List<Map<String, dynamic>> _candles = [];
  bool _loading = true;
  String? _error;
  Map<String, dynamic> _chart = {};

  String t(String ar, String en) => widget.english ? en : ar;

  @override
  void initState() {
    super.initState();
    _loadChart();
  }

  Future<void> _loadChart() async {
    final id = '${widget.trade['trade_id'] ?? widget.trade['position_id'] ?? widget.trade['id'] ?? ''}';
    if (id.isEmpty) {
      setState(() { _loading = false; _error = t('معرّف الصفقة غير متوفر.', 'Trade ID is missing.'); });
      return;
    }
    try {
      final result = await ApiService.tradeChart(tradeId: id);
      final raw = result['candles'];
      if (raw is! List || raw.isEmpty) {
        throw Exception(t('لا توجد شموع تاريخية لهذه الصفقة.', 'No historical candles were returned.'));
      }
      if (!mounted) return;
      setState(() {
        _chart = result;
        _candles = raw.whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item)).toList();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = '$e'; _loading = false; });
    }
  }

  Widget _metric(String label, dynamic value, Color color) => Expanded(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: widget.muted, fontSize: 10)),
        const SizedBox(height: 4),
        Text('${value ?? '—'}', style: TextStyle(
          color: color, fontWeight: FontWeight.w900, fontSize: 12,
        )),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final trade = widget.trade;
    final symbol = '${trade['symbol'] ?? '—'}';
    final direction = '${trade['direction'] ?? '—'}'.toUpperCase();
    final pnl = double.tryParse('${trade['net_pnl'] ?? trade['realized_pnl'] ?? 0}') ?? 0;
    final outcome = pnl > 0 ? t('صفقة رابحة', 'PROFIT') : pnl < 0 ? t('صفقة خاسرة', 'LOSS') : t('تعادل', 'BREAKEVEN');
    final timeframe = '${_chart['timeframe'] ?? trade['timeframe'] ?? (trade['context'] is Map ? (trade['context'] as Map)['timeframe'] : null) ?? '5m'}';

    return Directionality(
      textDirection: widget.english ? TextDirection.ltr : TextDirection.rtl,
      child: Scaffold(
        backgroundColor: widget.bg,
        appBar: AppBar(
          backgroundColor: widget.panel,
          foregroundColor: widget.text,
          title: Text(t('تفاصيل الصفقة', 'TRADE DETAILS')),
        ),
        body: ListView(
          padding: const EdgeInsets.all(14),
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: widget.panel,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: (pnl >= 0 ? const Color(0xFF21D6A1) : const Color(0xFFFF647C)).withOpacity(.35)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(child: Text(symbol, style: TextStyle(
                      color: widget.text, fontWeight: FontWeight.w900, fontSize: 20,
                    ))),
                    Text(direction, style: TextStyle(
                      color: direction == 'SHORT' ? const Color(0xFFFF647C) : const Color(0xFF21D6A1),
                      fontWeight: FontWeight.w900,
                    )),
                  ]),
                  const SizedBox(height: 10),
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
                      decoration: BoxDecoration(
                        color: (pnl > 0 ? const Color(0xFF21D6A1) : pnl < 0 ? const Color(0xFFFF647C) : const Color(0xFFF5A623)).withOpacity(.13),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: (pnl > 0 ? const Color(0xFF21D6A1) : pnl < 0 ? const Color(0xFFFF647C) : const Color(0xFFF5A623)).withOpacity(.45),
                        ),
                      ),
                      child: Text(outcome, style: TextStyle(
                        color: pnl > 0 ? const Color(0xFF21D6A1) : pnl < 0 ? const Color(0xFFFF647C) : const Color(0xFFF5A623),
                        fontWeight: FontWeight.w900, fontSize: 11,
                      )),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(children: [
                    _metric(t('الدخول', 'ENTRY'), trade['entry_price'] ?? trade['entry'], const Color(0xFF4287F5)),
                    _metric(t('الخروج', 'EXIT'), trade['close_price'] ?? trade['exit_price'], const Color(0xFFF5A623)),
                    _metric(t('النتيجة', 'NET PNL'), '${pnl >= 0 ? '+' : ''}${pnl.toStringAsFixed(4)} USDT',
                      pnl >= 0 ? const Color(0xFF21D6A1) : const Color(0xFFFF647C)),
                  ]),
                  const SizedBox(height: 10),
                  Row(children: [
                    _metric('STOP LOSS', trade['stop_loss'], const Color(0xFFFF647C)),
                    _metric('TAKE PROFIT', trade['take_profit'], const Color(0xFF21D6A1)),
                    _metric(t('الإطار', 'TIMEFRAME'), timeframe, widget.text),
                  ]),
                  const SizedBox(height: 8),
                  Text('${trade['close_reason'] ?? 'CLOSED'}',
                    style: TextStyle(color: widget.muted, fontSize: 10)),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Text(t('التشارت التاريخي ومستويات الصفقة', 'HISTORICAL TRADE CHART & LEVELS'),
              style: TextStyle(color: widget.text, fontWeight: FontWeight.w900)),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              constraints: const BoxConstraints(minHeight: 260),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: widget.panel,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF39A8FF).withOpacity(.25)),
              ),
              child: _loading
                  ? const SizedBox(height: 250, child: Center(child: CircularProgressIndicator()))
                  : _candles.isNotEmpty
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: InteractiveViewer(
                            minScale: 1,
                            maxScale: 5,
                            boundaryMargin: const EdgeInsets.all(60),
                            panEnabled: true,
                            scaleEnabled: true,
                            child: AspectRatio(
                              aspectRatio: 1.45,
                              child: CustomPaint(
                                painter: HistoricalTradeChartPainter(
                                candles: _candles,
                                symbol: symbol,
                                direction: direction,
                                timeframe: timeframe,
                                entry: _price(_chart['entry'] ?? trade['entry'] ?? trade['entry_price']),
                                exit: _price(_chart['exit'] ?? trade['exit_price'] ?? trade['close_price']),
                                stopLoss: _price(_chart['stop_loss'] ?? trade['stop_loss']),
                                  takeProfit: _price(_chart['take_profit'] ?? trade['take_profit']),
                                entryTime: int.tryParse('${_chart['opened_at'] ?? ''}'),
                                exitTime: int.tryParse('${_chart['closed_at'] ?? ''}'),
                                ),
                              ),
                            ),
                          ),
                        )
                      : Padding(
                          padding: const EdgeInsets.all(18),
                          child: Text(
                            _error ?? t('تعذر إنشاء التشارت التاريخي.', 'Could not render historical chart.'),
                            style: const TextStyle(color: Color(0xFFFF647C)),
                          ),
                        ),
            ),
            const SizedBox(height: 10),
            Text(
              t('السهم الأزرق يحدد شمعة الدخول، والبرتقالي شمعة الخروج، والخط البنفسجي يربطهما. الأحمر = وقف الخسارة، والأخضر = جني الأرباح.',
                'Blue marker = entry candle, orange marker = exit candle, purple line connects them. Red = stop loss, green = take profit.'),
              style: TextStyle(color: widget.muted, fontSize: 11, height: 1.5),
            ),
            if (_chart['timeframe_recorded'] == false)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                  t('هذه صفقة قديمة لم يكن إطارها الزمني محفوظاً؛ يظهر 5m كقيمة افتراضية وليست مؤكدة.',
                    'This legacy trade has no saved timeframe; 5m is shown as a fallback, not a verified value.'),
                  style: const TextStyle(color: Color(0xFFF5A623), fontSize: 10),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
