// Polyfill from https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/keys
if (!Object.keys) {
  Object.keys = (function() {
    'use strict';
    var hasOwnProperty = Object.prototype.hasOwnProperty,
        hasDontEnumBug = !({ toString: null }).propertyIsEnumerable('toString'),
        dontEnums = [
          'toString',
          'toLocaleString',
          'valueOf',
          'hasOwnProperty',
          'isPrototypeOf',
          'propertyIsEnumerable',
          'constructor'
        ],
        dontEnumsLength = dontEnums.length;

    return function(obj) {
      if (typeof obj !== 'object' && (typeof obj !== 'function' || obj === null)) {
        throw new TypeError('Object.keys called on non-object');
      }

      var result = [], prop, i;

      for (prop in obj) {
        if (hasOwnProperty.call(obj, prop)) {
          result.push(prop);
        }
      }

      if (hasDontEnumBug) {
        for (i = 0; i < dontEnumsLength; i++) {
          if (hasOwnProperty.call(obj, dontEnums[i])) {
            result.push(dontEnums[i]);
          }
        }
      }
      return result;
    };
  }());
}

function zeroPad(num) {
  if (num.toString().length == 1) {
    return "0" + num.toString();
  }
  return num.toString();
}

function S3DirectPost(uploadFile, presignUrl, keyCallback) {
  this.presignUrl = presignUrl;
  this.uploadFile = uploadFile;
  this.keyCallback = keyCallback;

  _this = this;

  this.submitToS3 = function() {
    console.log(this.presignUrl);
    console.log("started");

    var form = new FormData();
    var req = new XMLHttpRequest();


    console.log(uploadFile.files[0].name);

    var today = new Date();
    var dateStr = today.getFullYear().toString() + zeroPad(today.getMonth()+1) + zeroPad(today.getDate());
    var s3Key = dateStr + "/recordings/" + uploadFile.files[0].name;
    form.append('file-name', s3Key);
    form.append('file-type', uploadFile.files[0].type);
    form.append('csrf_token', csrftoken);

    req.open("POST", this.presignUrl, true);

    req.onerror = function(e) {
      console.log("error occured: " + e);
    };

    req.onload = function() {
      console.log(this.responseText);
      var resp = JSON.parse(this.responseText);
      if (this.status === 200) {
        _this.s3Post(uploadFile.files[0], resp['url'], resp['fields']);
      }
    };

    req.send(form);
  };

  this.s3Post = function(file, url, data) {
    var req = new XMLHttpRequest();
    var form = new FormData();
    // Removing unneeded key
    delete data['acl'];
    Object.keys(data).forEach(function(key) {
      form.append(key, data[key]);
    });

    form.append('file', file);
    req.open("POST", url, true);

    req.onerror = function(e) {
      console.log("an error occured: " + e);
    };

    req.onload = function() {
      console.log(this.responseText);
      // TODO: Figure out why this has changed
      var xml = new DOMParser().parseFromString(this.responseText, 'text/xml');
    };

    // TODO: Add custom event to listen to for progress bar
    req.upload.onprogress = function(data) {
      var pct = Math.round(data.loaded * 100 / data.total);
      console.log(pct);
    };

    req.send(form);
  };
}

function triggerUpload() {
  var uploadInput = document.querySelector("input[type='file']");
  if (uploadInput.files[0]) {
    var s3Post = new S3DirectPost(uploadInput, ZAPPA_HOST, function() { console.log('finished'); });
    s3Post.submitToS3();
  }
}

(function() {
  var uploadButton = document.getElementById("upload");
  if (uploadButton) {
    uploadButton.addEventListener("click", triggerUpload);
  };
})()
