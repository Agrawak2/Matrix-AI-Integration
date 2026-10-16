using System;
using System.IO;
using System.Net;
using System.Text;
using System.Web.Script.Serialization;

namespace IGT.Tools.Matrix.Rest
{
    public class MatrixMqlRestClient
    {
        private readonly string _passportUrl;
        private readonly string _spaceUrl;
        private readonly string _serviceName;
        private readonly string _serviceSecret;
        //private readonly string _securityContext;

        public MatrixMqlRestClient(
            string passportUrl,
            string spaceUrl,
            string serviceName,
            string serviceSecret)
        {
            _passportUrl = passportUrl;
            _spaceUrl = spaceUrl;
            _serviceName = serviceName;
            _serviceSecret = serviceSecret;
            //_securityContext = securityContext;
        }

        /// <summary>
        /// SOAP executeMQL replacement
        /// </summary>
        public string ExecuteMql(string mql)
        {
            // STEP 1 – Get transient token
            TransientToken transient = GetTransientToken();

            // STEP 2 – CAS authentication
            string serviceTicket = AuthenticateWithCas(transient.access_token);

            // STEP 3 – Execute MQL
            return ExecuteMqlRest(mql, serviceTicket);
        }

        #region Step 1: Batch Transient Token

        private TransientToken GetTransientToken()
        {
            string url =
                _passportUrl +
                "/api/v2/batch/ticket?service=" +
                _spaceUrl +
                "&identifier=agrawaa";

            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.Method = "GET";
            request.Headers["DS-SERVICE-NAME"] = _serviceName;
            request.Headers["DS-SERVICE-SECRET"] = _serviceSecret;
            request.Accept = "application/json";

            string json = ReadResponse(request);
            return Deserialize<TransientToken>(json);
        }

        #endregion

        #region Step 2: CAS Authentication

        private string AuthenticateWithCas(string transientToken)
        {
            string url =
                _passportUrl +
                "/api/login/cas/transient?tgt=" +
                transientToken +
                "&service=" +
                Uri.EscapeDataString(_spaceUrl);

            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.Method = "GET";
            request.Accept = "application/json";

            string json = ReadResponse(request);
            CasAuthResponse response = Deserialize<CasAuthResponse>(json);

            return response.access_token; // ST-xxxxx
        }

        #endregion

        #region Step 3: Execute MQL

        private string ExecuteMqlRest(string mql, string ticket)
        {
            string url =
                _spaceUrl +
                "/resources/IGT/v1/MQLService/executeMQL?query=" +
                Uri.EscapeDataString(mql) +
                "&ticket=" +
                ticket;

            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.Method = "GET";
            //request.Headers["SecurityContext"] = _securityContext;
            request.Accept = "application/json";

            return ReadResponse(request); // plain text
        }

        #endregion

        #region Helpers

        private string ReadResponse(HttpWebRequest request)
        {
            using (HttpWebResponse response =
                (HttpWebResponse)request.GetResponse())
            using (StreamReader reader =
                new StreamReader(response.GetResponseStream()))
            {
                return reader.ReadToEnd();
            }
        }

        private T Deserialize<T>(string json)
        {

            System.Web.Script.Serialization.JavaScriptSerializer serializer =
                new System.Web.Script.Serialization.JavaScriptSerializer();

            return serializer.Deserialize<T>(json);
        }

        #endregion

       
    }
}
