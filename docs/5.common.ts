import CryptoJS from "crypto-js";
import md5 from "md5";
// 定义常量
const appkey = "5589d41f92a597d016b037ac37db243d";
const key = CryptoJS.enc.Utf8.parse("2acf7e91e9864673");
const iv = CryptoJS.enc.Utf8.parse("1c29882d3ddfcfd6");
const media_key = CryptoJS.enc.Utf8.parse("f5d965df75336270");
const media_iv = CryptoJS.enc.Utf8.parse("97b60394abc2fbe1");

const sha256 = (data: string): string => CryptoJS.SHA256(data).toString();

const seralizeOrdered = (params: any) => {
  const keyValues = [
    `data=${params["data"]}`,
    `timestamp=${params["timestamp"]}`,
  ];
  const spliceString = `${keyValues.join("&")}${appkey}`;
  const digest = sha256(spliceString);
  return md5(digest);
};

// 加密
const encrypts = (
  data: string,
  key: CryptoJS.lib.WordArray,
  iv: CryptoJS.lib.WordArray
): string => {
  const preprocessing = CryptoJS.AES.encrypt(data, key, {
    iv,
    mode: CryptoJS.mode.CBC,
    padding: CryptoJS.pad.Pkcs7,
  }).toString();
  const timestamp = Math.floor(Date.now() / 1000);
  const sign = seralizeOrdered({ data: preprocessing, timestamp: timestamp });
  return `timestamp=${timestamp}&data=${preprocessing}&sign=${sign}`;
};

// 解密
const decrypts = (
  ciphertext: string,
  key: CryptoJS.lib.WordArray,
  iv: CryptoJS.lib.WordArray,
  padding = CryptoJS.pad.Pkcs7,
  enc = CryptoJS.enc.Utf8
): string => {
  return CryptoJS.AES.decrypt(ciphertext, key, {
    iv,
    mode: CryptoJS.mode.CBC,
    padding: padding,
  }).toString(enc);
};

const encryptData = (query: string): string => encrypts(query, key, iv);
const decryptData = (query: string): string => decrypts(query, key, iv);
const encryptMedia = (mediaData: string): string =>
  encrypts(mediaData, media_key, media_iv);
const decryptMedia = (encryptedMediaData: string): string =>
  decrypts(
    encryptedMediaData,
    media_key,
    media_iv,
    CryptoJS.pad.NoPadding,
    CryptoJS.enc.Base64
  );

export { encryptData, decryptData, encryptMedia, decryptMedia };
