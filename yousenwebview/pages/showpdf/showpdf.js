Page({
  data: {
    pdfFiles: [], // PDF文件列表
    loading: true, // 加载状态
    errorMsg: '' // 错误信息
  },

  onLoad() {
    // 初始化PDF文件列表
    this.initPdfList();
  },

  // 初始化PDF文件列表
  initPdfList() {
    // 模拟从服务器获取的在线PDF文件列表
    const onlinePdfs = [
      {
        id: 1,
        name: "2025一级建造师考试大纲.pdf",
        url: "https://example.com/pdf/2025-exam-outline.pdf", // 替换为实际URL
        size: "2.4MB",
        type: "online"
      },
      {
        id: 2,
        name: "一级建造师历年真题解析.pdf",
        url: "https://example.com/pdf/past-exams-analysis.pdf", // 替换为实际URL
        size: "5.7MB",
        type: "online"
      },
      {
        id: 3,
        name: "建筑工程管理与实务考点汇总.pdf",
        url: "https://example.com/pdf/construction-management.pdf", // 替换为实际URL
        size: "3.2MB",
        type: "online"
      },
      {
        id: 4,
        name: "一级建造师法律法规汇编.pdf",
        url: "https://example.com/pdf/laws-regulations.pdf", // 替换为实际URL
        size: "4.8MB",
        type: "online"
      }
    ];

    // 可以从本地存储中获取之前添加的本地PDF文件
    const localPdfs = wx.getStorageSync('localPdfs') || [];
    
    // 合并在线PDF和本地PDF
    const allPdfs = [...onlinePdfs, ...localPdfs];
    
    this.setData({
      pdfFiles: allPdfs,
      loading: false
    });
  },

  // 预览PDF文件
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
      // 在线PDF需要先下载
      wx.downloadFile({
        url: pdfFile.url,
        success: res => {
          wx.hideLoading();
          
          // 检查下载状态
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
      // 本地PDF直接预览
      filePath = pdfFile.path;
      wx.hideLoading();
      this.openPdfDocument(filePath);
    }
  },

  // 打开PDF文档
  openPdfDocument(filePath) {
    if (!filePath) {
      this.setData({ errorMsg: '文件路径不存在' });
      return;
    }
    
    wx.openDocument({
      fileType: 'pdf',
      filePath: filePath,
      showMenu: true, // 显示菜单，支持保存等操作
      success: res => {
        console.log('打开PDF成功', res);
      },
      fail: err => {
        console.error('打开PDF失败:', err);
        this.setData({ errorMsg: '打开PDF失败: ' + (err.errMsg || '未知错误') });
      }
    });
  },

  // 选择本地PDF文件
  chooseLocalPdf() {
    wx.chooseMessageFile({
      count: 1, // 最多选择1个文件
      type: 'file',
      extension: ['.pdf'], // 只允许选择PDF文件
      success: res => {
        // 获取选中的文件
        const tempFile = res.tempFiles[0];
        
        // 验证文件类型
        if (!tempFile.name.toLowerCase().endsWith('.pdf')) {
          this.setData({ errorMsg: '请选择PDF格式的文件' });
          return;
        }
        
        // 构造新的PDF文件对象
        const newPdf = {
          id: Date.now(), // 使用时间戳作为唯一ID
          name: tempFile.name,
          path: tempFile.path,
          size: this.formatFileSize(tempFile.size),
          type: "local",
          addedTime: new Date().toISOString()
        };
        
        // 更新PDF列表
        const updatedPdfs = [...this.data.pdfFiles, newPdf];
        this.setData({ pdfFiles: updatedPdfs });
        
        // 保存到本地存储，以便下次打开时仍能看到
        const localPdfs = wx.getStorageSync('localPdfs') || [];
        localPdfs.push(newPdf);
        wx.setStorageSync('localPdfs', localPdfs);
        
        // 自动预览刚添加的PDF
        this.openPdfDocument(newPdf.path);
      },
      fail: err => {
        console.error('选择文件失败:', err);
        // 用户取消选择不会显示错误
        if (err.errMsg !== 'chooseMessageFile:fail cancel') {
          this.setData({ errorMsg: '选择文件失败: ' + (err.errMsg || '未知错误') });
        }
      }
    });
  },

  // 格式化文件大小显示
  formatFileSize(bytes) {
    if (bytes < 1024) return bytes + 'B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
    else return (bytes / 1048576).toFixed(1) + 'MB';
  }
})
    