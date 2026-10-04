#pragma once

#include <QButtonGroup>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLayout>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QProgressBar>
#include <QPushButton>
#include <QResizeEvent>
#include <functional>

namespace retina::ui {

inline QLabel *text(QString value, int pixels = 14, bool bold = false, QString color = "#181d18") {
    auto *w = new QLabel(value);
    w->setWordWrap(true);
    QFont f(bold ? "Manrope" : "Atkinson Hyperlegible Next");
    f.setPixelSize(pixels); f.setBold(bold); w->setFont(f);
    w->setStyleSheet("color:" + color + "; background:transparent; border:0;");
    w->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Minimum);
    return w;
}
inline QLabel *icon(QString name, int pixels = 20, QString color = "#005227") {
    auto *w = text(name, pixels, false, color);
    QFont f("Material Symbols Outlined"); f.setPixelSize(pixels); w->setFont(f);
    w->setWordWrap(false); w->setFixedSize(pixels + 4, pixels + 4); return w;
}
inline QIcon buttonIcon(QString name,QString color="#005227") {
    QPixmap pix(24,24); pix.fill(Qt::transparent); QPainter p(&pix);
    QFont font("Material Symbols Outlined"); font.setPixelSize(20); p.setFont(font); p.setPen(QColor(color));
    p.drawText(pix.rect(),Qt::AlignCenter,name); return QIcon(pix);
}
inline QLabel *pill(QString value, QString background = "#f6fbf3", QString color = "#181d18") {
    auto *w = text(value, 12, true, color); w->setWordWrap(false);
    w->setStyleSheet(QString("background:%1; color:%2; border:1px solid #6f7a6f; border-radius:12px; padding:5px 12px;").arg(background,color));
    w->setSizePolicy(QSizePolicy::Maximum, QSizePolicy::Fixed); return w;
}
inline QProgressBar *meter(double value, int height = 8) {
    auto *w = new QProgressBar; w->setRange(0,1000); w->setValue(qBound(0,int(value*1000),1000));
    w->setTextVisible(false); w->setFixedHeight(height);
    w->setStyleSheet(QString("QProgressBar { background:#dfe4dc; border:1px solid #6f7a6f; border-radius:%1px; } QProgressBar::chunk { background:#005227; border-radius:%1px; }").arg(height/2)); return w;
}

// The source uses flex-wrap for controls. Preserve order and wrap whole groups.
class FlowLayout : public QLayout {
public:
    explicit FlowLayout(QWidget *parent, int gap = 12) : QLayout(parent), gap_(gap) { setContentsMargins(0,0,0,0); }
    ~FlowLayout() override { while (auto *i=takeAt(0)) delete i; }
    void addItem(QLayoutItem *i) override { items_.append(i); }
    int count() const override { return int(items_.size()); }
    QLayoutItem *itemAt(int i) const override { return items_.value(i); }
    QLayoutItem *takeAt(int i) override { return i>=0 && i<items_.size() ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return {}; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return arrange(QRect(0,0,w,0),false); }
    QSize sizeHint() const override { return minimumSize(); }
    QSize minimumSize() const override { QSize s; for(auto *i:items_) s=s.expandedTo(i->minimumSize()); return s; }
    void setGeometry(const QRect &r) override { QLayout::setGeometry(r); arrange(r,true); }
private:
    int arrange(QRect r, bool apply) const {
        int x=r.x(), y=r.y(), line=0;
        for(auto *i:items_) {
            QSize s=i->sizeHint(); s.setWidth(qMin(s.width(),r.width()));
            if(x>r.x() && x+s.width()>r.right()+1) { x=r.x(); y+=line+gap_; line=0; }
            if(apply) i->setGeometry(QRect(QPoint(x,y),s));
            x+=s.width()+gap_; line=qMax(line,s.height());
        }
        return y-r.y()+line;
    }
    QList<QLayoutItem*> items_; int gap_;
};

inline QWidget *segmented(QString name, QStringList options, QString value, QObject *context,
                           std::function<void(QString)> changed, bool wide=false) {
    auto *w=new QFrame; w->setObjectName("Segmented"); w->setAccessibleName(name);
    w->setStyleSheet("QFrame#Segmented { background:#f0f5ed; border:1px solid #becabd; border-radius:8px; } QPushButton { background:transparent; color:#3f4940; border:0; border-radius:6px; padding:8px 12px; font-size:14px; font-weight:600; } QPushButton:hover { background:#e5eae2; } QPushButton:checked { background:#005227; color:white; } QPushButton:focus { border:1px solid #005227; }");
    auto *row=new QHBoxLayout(w); row->setContentsMargins(4,4,4,4); row->setSpacing(4);
    auto *group=new QButtonGroup(w); group->setExclusive(true);
    for(const auto &option:options) {
        auto *b=new QPushButton(option); b->setCheckable(true); b->setChecked(option==value);
        b->setAccessibleName(name+": "+option); b->setMinimumHeight(wide?44:34);
        b->setCursor(Qt::PointingHandCursor); group->addButton(b); row->addWidget(b,wide?1:0);
        QObject::connect(b,&QPushButton::clicked,context,[changed,option] { changed(option); });
    }
    w->setSizePolicy(wide?QSizePolicy::Expanding:QSizePolicy::Maximum,QSizePolicy::Fixed);
    return w;
}

// CSS breakpoints refer to the viewport, not the width of the centered content.
class ResponsiveGrid : public QWidget {
public:
    ResponsiveGrid(int gap=24, bool singleRow=false, QList<int> weights={},bool stretchCells=false) : single_(singleRow), weights_(weights),stretch_(stretchCells) {
        grid_=new QGridLayout(this); grid_->setContentsMargins(0,0,0,0); grid_->setSpacing(gap);
        setSizePolicy(QSizePolicy::Expanding,QSizePolicy::Minimum);
    }
    void append(QWidget *w) { widgets_.append(w); w->setParent(this); rearrange(); }
protected:
    void resizeEvent(QResizeEvent *e) override { QWidget::resizeEvent(e); rearrange(); }
private:
    void rearrange() {
        const int viewport=window()->width();
        const int cols=single_ ? (viewport>=1024?int(widgets_.size()):1) : (viewport>=1024?3:viewport>=768?2:1);
        if(cols==columns_ && grid_->count()==widgets_.size()) return;
        while(auto *item=grid_->takeAt(0)) delete item;
        for(int i=0;i<6;++i) grid_->setColumnStretch(i,0);
        for(int i=0;i<widgets_.size();++i) grid_->addWidget(widgets_[i],i/cols,i%cols,stretch_?Qt::Alignment():Qt::AlignTop);
        for(int i=0;i<cols;++i) grid_->setColumnStretch(i,weights_.value(i,1));
        columns_=cols;
    }
    QGridLayout *grid_; QList<QWidget*> widgets_; bool single_; QList<int> weights_; bool stretch_; int columns_=0;
};

class ImageStage : public QWidget {
public:
    QImage image;
    QString status;
    std::function<void(QPointF)> pointSelected;
    std::function<void(QPointF)> pointMoved;
    ImageStage() { setObjectName("ImageStage"); setMouseTracking(true); setFocusPolicy(Qt::StrongFocus); setSizePolicy(QSizePolicy::Expanding,QSizePolicy::Preferred); }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return w*3/4; }
    QSize sizeHint() const override { return {640,480}; }
    QSize minimumSizeHint() const override { return {200,150}; }
    QRectF imageRect() const {
        const QSizeF s=image.size().scaled(size()-QSize(4,4),Qt::KeepAspectRatio);
        return QRectF((width()-s.width())/2,(height()-s.height())/2,s.width(),s.height());
    }
protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this); p.setRenderHint(QPainter::Antialiasing);
        QPainterPath shape; shape.addRoundedRect(QRectF(rect()).adjusted(1,1,-1,-1),12,12);
        p.fillPath(shape,Qt::black); p.setClipPath(shape);
        if(!image.isNull()) p.drawImage(imageRect(),image);
        if(!status.isEmpty()) {
            QFont f("Atkinson Hyperlegible Next"); f.setPixelSize(14); p.setFont(f);
            QRect note=rect().adjusted(16,height()-100,-16,-16);
            p.fillRect(note,QColor(0,0,0,220)); p.setPen(Qt::white);
            p.drawText(note.adjusted(12,8,-12,-8),Qt::TextWordWrap,status);
        }
        p.setClipping(false); p.setPen(QPen(QColor("#6f7a6f"),2)); p.drawPath(shape);
    }
    QPointF normalized(QPointF pt) const { auto r=imageRect(); return {(pt.x()-r.x())/r.width(),(pt.y()-r.y())/r.height()}; }
    void mousePressEvent(QMouseEvent *e) override { if(pointSelected && imageRect().contains(e->position())) pointSelected(normalized(e->position())); }
    void mouseMoveEvent(QMouseEvent *e) override { if(pointMoved && imageRect().contains(e->position())) pointMoved(normalized(e->position())); }
};
} // namespace retina::ui
