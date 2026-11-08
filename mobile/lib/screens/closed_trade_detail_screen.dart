import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

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
  Uint8List? _image;
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
      final encoded = result['image_base64'];
      if (encoded is! String || encoded.isEmpty) {
        throw Exception(t('لم تصل صورة التشارت من الخادم.', 'Chart image was not returned.'));
      }
      if (!mounted) return;
      setState(() {
        _chart = result;
        _image = base64Decode(encoded);
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
                  const SizedBox(height: 12),
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
            Text(t('صورة التشارت وقت الصفقة', 'TRADE-TIME CHART SNAPSHOT'),
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
                  : _image != null
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: Image.memory(_image!, fit: BoxFit.contain),
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
              t('الخط الأزرق = الدخول، البرتقالي = الخروج، الأحمر = وقف الخسارة، والأخضر = جني الأرباح.',
                'Blue = entry, orange = exit, red = stop loss, green = take profit.'),
              style: TextStyle(color: widget.muted, fontSize: 11, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }
}
