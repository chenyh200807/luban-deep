Page({
  data: {
    pdfFiles: [],
    loading: true,
    errorMsg: ''
  },

  onLoad() {
    this.initPdfList();
  },

  initPdfList() {
    const localPdfs = wx.getStorageSync('localPdfs') || [];

    this.setData({
      pdfFiles: localPdfs,
      loading: false
    });
  },

  previewPdf(e) {
    const index = e.currentTarget.dataset.index;
    const pdfFile = this.data.pdfFiles[index];
    let filePath = '';

    this.setData({ errorMsg: '' });

    if (!pdfFile) {
      this.setData({ errorMsg: '未找到该PDF文件' });
      return;
    }

    wx.showLoading({ title: '准备预览...' });

    if (pdfFile.type === 'online') {
      wx.downloadFile({
        url: pdfFile.url,
        success: res => {
          wx.hideLoading();

          if (res.statusCode !== 200) {
            this.setData({ errorMsg: '下载PDF失败，请稍后重试' });
            return;
          }

          filePath = res.tempFilePath;
          this.openPdfDocument(filePath);
        },
        fail: err => {
          wx.hideLoading();
          console.error('下载失败:', err);
          this.setData({ errorMsg: '下载PDF失败: ' + (err.errMsg || '未知错误') });
        }
      });
    } else {
      filePath = pdfFile.path;
      wx.hideLoading();
      this.openPdfDocument(filePath);
    }
  },

  openPdfDocument(filePath) {
    if (!filePath) {
      this.setData({ errorMsg: '文件路径不存在' });
      return;
    }
    
    wx.openDocument({
      fileType: 'pdf',
      filePath: filePath,
      showMenu: true,
      fail: err => {
        console.error('打开PDF失败:', err);
        this.setData({ errorMsg: '打开PDF失败: ' + (err.errMsg || '未知错误') });
      }
    });
  },

  chooseLocalPdf() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['.pdf'],
      success: res => {
        const tempFile = res.tempFiles[0];

        if (!tempFile.name.toLowerCase().endsWith('.pdf')) {
          this.setData({ errorMsg: '请选择PDF格式的文件' });
          return;
        }

        const newPdf = {
          id: Date.now(),
          name: tempFile.name,
          path: tempFile.path,
          size: this.formatFileSize(tempFile.size),
          type: "local",
          addedTime: new Date().toISOString()
        };

        const updatedPdfs = [...this.data.pdfFiles, newPdf];
        this.setData({ pdfFiles: updatedPdfs });

        const localPdfs = wx.getStorageSync('localPdfs') || [];
        localPdfs.push(newPdf);
        wx.setStorageSync('localPdfs', localPdfs);

        this.openPdfDocument(newPdf.path);
      },
      fail: err => {
        console.error('选择文件失败:', err);
        if (err.errMsg !== 'chooseMessageFile:fail cancel') {
          this.setData({ errorMsg: '选择文件失败: ' + (err.errMsg || '未知错误') });
        }
      }
    });
  },

  formatFileSize(bytes) {
    if (bytes < 1024) return bytes + 'B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
    else return (bytes / 1048576).toFixed(1) + 'MB';
  }
})
